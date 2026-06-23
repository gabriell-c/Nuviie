import json
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from leads.models import Lead

from .models import WhatsAppInstance, WhatsAppMessage
from .serializers import WhatsAppInstanceSerializer, WhatsAppMessageSerializer
from .services import (
    EvolutionClient,
    EvolutionError,
    dispatch_text,
    get_default_instance,
    normalize_number,
    store_incoming_message,
)

logger = logging.getLogger('whatsapp')


def _webhook_url():
    base = (getattr(settings, 'NUVIIE_PUBLIC_BASE_URL', '') or '').rstrip('/')
    return f"{base}/api/whatsapp/webhook/"


def _webhook_token():
    return getattr(settings, 'WHATSAPP_WEBHOOK_TOKEN', '') or ''


# ── Instâncias ────────────────────────────────────────────────────────────────
class WhatsAppInstanceViewSet(viewsets.ModelViewSet):
    serializer_class = WhatsAppInstanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return WhatsAppInstance.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        instance = serializer.save(user=self.request.user)
        # Garante que exista um padrão.
        if not WhatsAppInstance.objects.filter(user=self.request.user, is_default=True).exists():
            instance.is_default = True
            instance.save(update_fields=['is_default'])

    @action(detail=True, methods=['post'], url_path='connect')
    def connect(self, request, pk=None):
        """Cria a instância no Evolution (se necessário) e retorna o QR Code."""
        inst = self.get_object()
        client = EvolutionClient(inst)
        if not client.configured:
            return Response(
                {'error': 'Evolution API não configurado. Defina EVOLUTION_API_URL e EVOLUTION_API_KEY.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            # create_instance é idempotente o suficiente: se já existe, caímos no connect.
            try:
                client.create_instance(
                    number=inst.phone_number,
                    webhook_url=_webhook_url() if _webhook_token() else '',
                    webhook_token=_webhook_token(),
                )
            except EvolutionError as exc:
                logger.info('create_instance falhou (provavelmente já existe): %s', exc)
            data = client.connect(inst.phone_number)
        except EvolutionError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        qr = data.get('base64') or (data.get('qrcode') or {}).get('base64', '')
        pairing = data.get('pairingCode') or (data.get('qrcode') or {}).get('pairingCode', '')
        inst.status = 'connecting'
        if qr:
            inst.last_qr_base64 = qr
        inst.save(update_fields=['status', 'last_qr_base64', 'updated_at'])
        return Response({'qr': qr, 'pairing_code': pairing, 'status': inst.status})

    @action(detail=True, methods=['get'], url_path='state')
    def state(self, request, pk=None):
        """Consulta o estado de conexão no Evolution e sincroniza o status local."""
        inst = self.get_object()
        client = EvolutionClient(inst)
        if not client.configured:
            return Response({'status': inst.status, 'configured': False})
        try:
            data = client.connection_state()
        except EvolutionError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        state = (data.get('instance') or {}).get('state') or data.get('state') or ''
        mapping = {'open': 'connected', 'connecting': 'connecting', 'close': 'disconnected'}
        new_status = mapping.get(state, inst.status)
        fields = ['status', 'updated_at']
        inst.status = new_status
        if new_status == 'connected':
            inst.last_connected_at = timezone.now()
            inst.last_qr_base64 = ''
            fields += ['last_connected_at', 'last_qr_base64']
        inst.save(update_fields=fields)
        return Response({'status': inst.status, 'raw_state': state})

    @action(detail=True, methods=['post'], url_path='set-default')
    def set_default(self, request, pk=None):
        inst = self.get_object()
        WhatsAppInstance.objects.filter(user=request.user).update(is_default=False)
        inst.is_default = True
        inst.save(update_fields=['is_default'])
        return Response(WhatsAppInstanceSerializer(inst).data)

    @action(detail=True, methods=['post'], url_path='logout')
    def logout(self, request, pk=None):
        inst = self.get_object()
        client = EvolutionClient(inst)
        try:
            client.logout()
        except EvolutionError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        inst.status = 'disconnected'
        inst.last_qr_base64 = ''
        inst.save(update_fields=['status', 'last_qr_base64', 'updated_at'])
        return Response({'status': inst.status})


# ── Mensagens ─────────────────────────────────────────────────────────────────
class WhatsAppMessageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WhatsAppMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = WhatsAppMessage.objects.filter(user=self.request.user)
        lead_id = self.request.query_params.get('lead')
        phone = self.request.query_params.get('phone')
        if lead_id:
            qs = qs.filter(lead_id=lead_id)
        if phone:
            qs = qs.filter(phone=normalize_number(phone))
        return qs.select_related('lead', 'instance')

    @action(detail=False, methods=['get'], url_path='conversations')
    def conversations(self, request):
        """Lista as conversas (agrupadas por telefone) com a última mensagem."""
        base = WhatsAppMessage.objects.filter(user=request.user)
        last_ids = (
            base.values('phone')
            .annotate(last_id=Max('id'))
            .values_list('last_id', flat=True)
        )
        rows = (
            WhatsAppMessage.objects.filter(id__in=list(last_ids))
            .select_related('lead')
            .order_by('-created_at')
        )
        data = []
        for m in rows:
            unread = base.filter(phone=m.phone, direction='in', status='received').count()
            data.append({
                'phone': m.phone,
                'contact_name': m.contact_name or (m.lead.name if m.lead else m.phone),
                'lead_id': m.lead_id,
                'last_text': m.text or f'[{m.get_message_type_display()}]',
                'last_direction': m.direction,
                'last_at': m.created_at.strftime('%d/%m %H:%M'),
                'unread': unread,
            })
        return Response({'conversations': data})

    @action(detail=False, methods=['post'], url_path='send')
    def send(self, request):
        """Envia uma mensagem de texto e registra no histórico."""
        text = (request.data.get('text') or '').strip()
        phone = normalize_number(request.data.get('phone') or '')
        lead_id = request.data.get('lead')
        instance_id = request.data.get('instance')

        lead = None
        if lead_id:
            lead = Lead.objects.filter(user=request.user, id=lead_id).first()
            if lead and not phone:
                phone = normalize_number(lead.normalized_phone or lead.phone_number)

        if not text:
            return Response({'error': 'Mensagem vazia.'}, status=status.HTTP_400_BAD_REQUEST)
        if not phone:
            return Response({'error': 'Número de destino ausente.'}, status=status.HTTP_400_BAD_REQUEST)

        if instance_id:
            inst = WhatsAppInstance.objects.filter(user=request.user, id=instance_id).first()
        else:
            inst = get_default_instance(request.user)
        if not inst:
            return Response(
                {'error': 'Nenhum número WhatsApp conectado. Configure uma instância primeiro.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        msg = dispatch_text(request.user, inst, phone, text, lead=lead)
        if msg.status == 'failed':
            return Response({'error': msg.error, 'message': WhatsAppMessageSerializer(msg).data},
                            status=status.HTTP_502_BAD_GATEWAY)
        return Response(WhatsAppMessageSerializer(msg).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='suggest')
    def suggest(self, request):
        """Gera um rascunho de resposta com a IA (não envia) para você revisar."""
        from ai.service import AIUnavailable, busy_message
        from .ai_reply import generate_draft

        phone = normalize_number(request.data.get('phone') or '')
        lead_id = request.data.get('lead')
        instance_id = request.data.get('instance')

        if not phone and lead_id:
            lead = Lead.objects.filter(user=request.user, id=lead_id).first()
            if lead:
                phone = normalize_number(lead.normalized_phone or lead.phone_number)
        if not phone:
            return Response({'error': 'Número de destino ausente.'}, status=status.HTTP_400_BAD_REQUEST)

        if instance_id:
            inst = WhatsAppInstance.objects.filter(user=request.user, id=instance_id).first()
        else:
            inst = get_default_instance(request.user)

        try:
            draft = generate_draft(request.user, inst, phone)
        except AIUnavailable:
            return Response(
                {'error': busy_message()},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({'draft': (draft or '').strip()})


# ── Webhook (Evolution → Nuviie) ──────────────────────────────────────────────
@csrf_exempt
@require_POST
def evolution_webhook(request):
    """Recebe eventos do Evolution API. Autenticado por Bearer token."""
    expected = _webhook_token()
    auth = request.headers.get('Authorization', '')
    token = auth[7:].strip() if auth.lower().startswith('bearer ') else auth.strip()
    if not expected or token != expected:
        return _json({'error': 'Token inválido.'}, 401)

    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return _json({'error': 'JSON inválido.'}, 400)

    event = (payload.get('event') or '').lower().replace('_', '.')
    instance_name = payload.get('instance') or payload.get('instanceName') or ''
    inst = WhatsAppInstance.objects.filter(instance_name=instance_name).first()
    user = inst.user if inst else _fallback_user()
    if not user:
        return _json({'ok': True, 'ignored': 'no_user'})

    if event in ('messages.upsert', 'messages.set'):
        data = payload.get('data') or {}
        items = data if isinstance(data, list) else [data]
        stored = 0
        last_msg = None
        for item in items:
            try:
                msg, created = store_incoming_message(user=user, instance=inst, payload_data=item)
                if created:
                    stored += 1
                    last_msg = msg
                    _notify_incoming(user, msg)
            except Exception:
                logger.exception('Falha ao armazenar mensagem recebida')

        # Auto-resposta por IA (opt-in por número). Roda em background.
        if last_msg and inst and inst.ai_autoreply_enabled and last_msg.text:
            try:
                from .ai_reply import autoreply_async
                autoreply_async(user, inst, last_msg.phone, lead=last_msg.lead)
            except Exception:
                logger.exception('Falha ao agendar auto-resposta WhatsApp')

        return _json({'ok': True, 'stored': stored})

    if event == 'connection.update' and inst:
        state = (payload.get('data') or {}).get('state', '')
        mapping = {'open': 'connected', 'connecting': 'connecting', 'close': 'disconnected'}
        if state in mapping:
            inst.status = mapping[state]
            if inst.status == 'connected':
                inst.last_connected_at = timezone.now()
                inst.last_qr_base64 = ''
            inst.save(update_fields=['status', 'last_connected_at', 'last_qr_base64', 'updated_at'])
        return _json({'ok': True, 'status': inst.status})

    return _json({'ok': True, 'event': event})


def _notify_incoming(user, msg):
    if not msg:
        return
    try:
        from notifications.models import Notification

        who = msg.contact_name or (msg.lead.name if msg.lead else msg.phone)
        Notification.objects.create(
            user=user,
            title=f'WhatsApp: {who}',
            message=(msg.text or '[mídia]')[:255],
            level='info',
            lead=msg.lead,
            dedupe_key=f'wa-{msg.evolution_id}' if msg.evolution_id else '',
        )
    except Exception:
        logger.debug('Notificação de WhatsApp não criada', exc_info=True)


def _fallback_user():
    username = getattr(settings, 'NUVIIE_EXTENSION_USER', '') or 'admin'
    User = get_user_model()
    return User.objects.filter(username=username).first() or User.objects.filter(is_superuser=True).first()


def _json(data, status_code=200):
    from django.http import JsonResponse
    return JsonResponse(data, status=status_code)


# ── Página ────────────────────────────────────────────────────────────────────
@login_required
def whatsapp_page(request):
    instances = WhatsAppInstance.objects.filter(user=request.user)
    return render(request, 'whatsapp/inbox.html', {
        'current_page': 'whatsapp',
        'instances': instances,
        'webhook_configured': bool(_webhook_token()),
    })
