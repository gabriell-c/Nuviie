"""Cliente e helpers de integração com o Evolution API (v2).

Documentação: https://doc.evolution-api.com/v2
Endpoints usados:
  - POST /instance/create
  - GET  /instance/connect/{instance}        (QR code / pairing)
  - GET  /instance/connectionState/{instance}
  - POST /instance/restart/{instance}
  - DELETE /instance/logout/{instance}
  - POST /webhook/set/{instance}
  - POST /message/sendText/{instance}
  - POST /message/sendMedia/{instance}
"""
import logging

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('whatsapp')

DEFAULT_TIMEOUT = 20

# Eventos mínimos para o CRM funcionar (recebimento + status de conexão).
WEBHOOK_EVENTS = [
    'MESSAGES_UPSERT',
    'MESSAGES_UPDATE',
    'SEND_MESSAGE',
    'CONNECTION_UPDATE',
    'QRCODE_UPDATED',
]


def normalize_number(phone) -> str:
    """Mantém apenas dígitos. Ex: +55 (11) 99999-9999 -> 5511999999999"""
    if not phone:
        return ''
    return ''.join(c for c in str(phone) if c.isdigit())


def jid_to_phone(jid: str) -> str:
    """Extrai o número de um remoteJid (ex: 5511999999999@s.whatsapp.net)."""
    if not jid:
        return ''
    return normalize_number(jid.split('@', 1)[0].split(':', 1)[0])


class EvolutionError(Exception):
    """Erro de comunicação/validação com o Evolution API."""


class EvolutionClient:
    """Wrapper REST do Evolution API para uma instância específica."""

    def __init__(self, instance=None, *, base_url=None, api_key=None, instance_name=None):
        self.instance = instance
        if instance is not None:
            self.base_url = (instance.api_url or getattr(settings, 'EVOLUTION_API_URL', '') or '').rstrip('/')
            self.api_key = instance.api_key or getattr(settings, 'EVOLUTION_API_KEY', '') or ''
            self.instance_name = instance.instance_name
        else:
            self.base_url = (base_url or getattr(settings, 'EVOLUTION_API_URL', '') or '').rstrip('/')
            self.api_key = api_key or getattr(settings, 'EVOLUTION_API_KEY', '') or ''
            self.instance_name = instance_name

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _looks_like_evolution_misconfig(self, resp) -> bool:
        """Detecta respostas que não vêm de um Evolution real (ex.: HTML do Django)."""
        content_type = (resp.headers.get('Content-Type') or '').lower()
        body_start = (resp.text or '').lstrip()[:200].lower()
        return (
            'text/html' in content_type
            or body_start.startswith('<!doctype')
            or body_start.startswith('<html')
        )

    def _request(self, method, path, *, json=None, params=None):
        if not self.configured:
            raise EvolutionError('Evolution API não configurado (URL/API key ausentes).')
        url = f"{self.base_url}{path}"
        headers = {'Content-Type': 'application/json', 'apikey': self.api_key}
        try:
            resp = requests.request(
                method, url, headers=headers, json=json, params=params, timeout=DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.exception('Falha de conexão com Evolution API')
            raise EvolutionError(f'Falha de conexão com o Evolution API: {exc}') from exc

        # A URL aponta para algo que não é um servidor Evolution (retornou HTML).
        if self._looks_like_evolution_misconfig(resp):
            logger.error(
                'Evolution API %s %s -> %s: resposta HTML (URL não é um servidor Evolution). base_url=%s',
                method, path, resp.status_code, self.base_url,
            )
            raise EvolutionError(
                f'EVOLUTION_API_URL ("{self.base_url}") não aponta para um servidor Evolution '
                f'(a resposta foi uma página HTML, não JSON). Verifique se o Evolution API está '
                f'rodando e ajuste EVOLUTION_API_URL para o endereço dele (ex.: http://localhost:8080).'
            )

        if resp.status_code not in (200, 201):
            detail = ''
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text[:300]
            logger.error('Evolution API %s %s -> %s: %s', method, path, resp.status_code, detail)
            raise EvolutionError(f'Evolution API retornou {resp.status_code}: {detail}')

        try:
            return resp.json()
        except ValueError:
            return {}

    # ── Instância ────────────────────────────────────────────────────────────
    def create_instance(self, *, number='', webhook_url='', webhook_token=''):
        payload = {
            'instanceName': self.instance_name,
            'qrcode': True,
            'integration': 'WHATSAPP-BAILEYS',
        }
        if number:
            payload['number'] = number
        if webhook_url:
            payload['webhook'] = {
                'url': webhook_url,
                'byEvents': False,
                'base64': False,
                'events': WEBHOOK_EVENTS,
            }
            if webhook_token:
                payload['webhook']['headers'] = {
                    'Authorization': f'Bearer {webhook_token}',
                    'Content-Type': 'application/json',
                }
        return self._request('POST', '/instance/create', json=payload)

    def connect(self, number=''):
        """Retorna QR code (base64) e/ou pairing code para conectar o número."""
        params = {'number': number} if number else None
        return self._request('GET', f'/instance/connect/{self.instance_name}', params=params)

    def connection_state(self):
        return self._request('GET', f'/instance/connectionState/{self.instance_name}')

    def restart(self):
        return self._request('POST', f'/instance/restart/{self.instance_name}')

    def logout(self):
        return self._request('DELETE', f'/instance/logout/{self.instance_name}')

    def set_webhook(self, webhook_url, webhook_token=''):
        payload = {
            'webhook': {
                'enabled': True,
                'url': webhook_url,
                'byEvents': False,
                'base64': False,
                'events': WEBHOOK_EVENTS,
            }
        }
        if webhook_token:
            payload['webhook']['headers'] = {
                'Authorization': f'Bearer {webhook_token}',
                'Content-Type': 'application/json',
            }
        return self._request('POST', f'/webhook/set/{self.instance_name}', json=payload)

    # ── Mensagens ────────────────────────────────────────────────────────────
    def send_text(self, number, text, *, delay=0, link_preview=True):
        payload = {'number': normalize_number(number), 'text': text}
        if delay:
            payload['delay'] = delay
        if not link_preview:
            payload['linkPreview'] = False
        return self._request('POST', f'/message/sendText/{self.instance_name}', json=payload)

    def send_media(self, number, media_url, *, media_type='image', caption='', mimetype='', file_name=''):
        payload = {
            'number': normalize_number(number),
            'mediatype': media_type,
            'media': media_url,
        }
        if caption:
            payload['caption'] = caption
        if mimetype:
            payload['mimetype'] = mimetype
        if file_name:
            payload['fileName'] = file_name
        return self._request('POST', f'/message/sendMedia/{self.instance_name}', json=payload)


# ── Helpers de domínio ───────────────────────────────────────────────────────

def get_default_instance(user):
    """Retorna a instância padrão (ou a primeira ativa) do usuário."""
    from .models import WhatsAppInstance

    qs = WhatsAppInstance.objects.filter(user=user, is_active=True)
    return qs.filter(is_default=True).first() or qs.first()


def dispatch_text(user, inst, phone, text, *, lead=None, delay=0):
    """Envia um texto via Evolution e registra no histórico (direction='out').

    Reutilizável pelo envio manual (inbox) e pela auto-resposta da IA. Nunca
    levanta: em caso de falha, o WhatsAppMessage volta com status='failed' e o
    erro preenchido, para o chamador decidir o que fazer.
    """
    from .models import WhatsAppMessage

    phone = normalize_number(phone)
    msg = WhatsAppMessage.objects.create(
        instance=inst, user=user, lead=lead,
        direction='out', phone=phone, message_type='text',
        text=text, status='pending', timestamp=timezone.now(),
    )

    client = EvolutionClient(inst)
    try:
        result = client.send_text(phone, text, delay=delay)
    except EvolutionError as exc:
        msg.status = 'failed'
        msg.error = str(exc)
        msg.save(update_fields=['status', 'error'])
        logger.warning('Falha ao enviar WhatsApp para %s: %s', phone, exc)
        return msg

    msg.status = 'sent'
    msg.evolution_id = (result.get('key') or {}).get('id', '') or ''
    msg.raw = result
    msg.save(update_fields=['status', 'evolution_id', 'raw'])
    return msg


def find_lead_by_phone(user, phone):
    """Tenta casar um número com um lead pelo normalized_phone (com tolerância de DDI/9)."""
    from leads.models import Lead

    digits = normalize_number(phone)
    if not digits:
        return None

    candidates = {digits}
    # Sem o DDI 55
    if digits.startswith('55') and len(digits) > 11:
        candidates.add(digits[2:])
    # Com o DDI 55
    if not digits.startswith('55'):
        candidates.add('55' + digits)
    # Tolerância do nono dígito (sufixo de 8 dígitos costuma bater)
    suffix = digits[-8:]

    qs = Lead.objects.filter(user=user)
    lead = qs.filter(normalized_phone__in=list(candidates)).first()
    if lead:
        return lead
    if len(suffix) == 8:
        return qs.filter(normalized_phone__endswith=suffix).first()
    return None


def _extract_message_content(message: dict):
    """Normaliza o objeto `message` do payload Evolution para (tipo, texto, media_url)."""
    if not isinstance(message, dict):
        return 'other', '', ''

    if 'conversation' in message:
        return 'text', message.get('conversation') or '', ''
    if 'extendedTextMessage' in message:
        return 'text', (message['extendedTextMessage'] or {}).get('text', ''), ''
    if 'imageMessage' in message:
        img = message['imageMessage'] or {}
        return 'image', img.get('caption', ''), img.get('url', '')
    if 'videoMessage' in message:
        vid = message['videoMessage'] or {}
        return 'video', vid.get('caption', ''), vid.get('url', '')
    if 'audioMessage' in message:
        return 'audio', '', (message['audioMessage'] or {}).get('url', '')
    if 'documentMessage' in message:
        doc = message['documentMessage'] or {}
        return 'document', doc.get('fileName', ''), doc.get('url', '')
    if 'stickerMessage' in message:
        return 'sticker', '', (message['stickerMessage'] or {}).get('url', '')
    if 'locationMessage' in message:
        loc = message['locationMessage'] or {}
        text = f"{loc.get('degreesLatitude', '')},{loc.get('degreesLongitude', '')}"
        return 'location', text, ''
    if 'contactMessage' in message:
        return 'contact', (message['contactMessage'] or {}).get('displayName', ''), ''
    return 'other', '', ''


def store_incoming_message(*, user, instance, payload_data: dict):
    """Cria um WhatsAppMessage a partir do `data` de um evento MESSAGES_UPSERT.

    Retorna (message, created). Ignora mensagens enviadas por nós (fromMe).
    """
    from .models import WhatsAppMessage

    key = payload_data.get('key') or {}
    if key.get('fromMe'):
        return None, False

    remote_jid = key.get('remoteJid', '') or ''
    # Ignora grupos por padrão (foco em leads 1:1).
    if remote_jid.endswith('@g.us'):
        return None, False

    evolution_id = key.get('id', '') or ''
    if evolution_id and WhatsAppMessage.objects.filter(
        user=user, evolution_id=evolution_id, direction='in',
    ).exists():
        existing = WhatsAppMessage.objects.get(
            user=user, evolution_id=evolution_id, direction='in',
        )
        return existing, False

    phone = jid_to_phone(remote_jid)
    msg_type, text, media_url = _extract_message_content(payload_data.get('message') or {})

    ts = payload_data.get('messageTimestamp')
    timestamp = None
    if ts:
        try:
            timestamp = timezone.datetime.fromtimestamp(int(ts), tz=timezone.get_current_timezone())
        except (ValueError, OSError, TypeError):
            timestamp = timezone.now()

    lead = find_lead_by_phone(user, phone)

    msg = WhatsAppMessage.objects.create(
        instance=instance,
        user=user,
        lead=lead,
        direction='in',
        remote_jid=remote_jid,
        phone=phone,
        contact_name=payload_data.get('pushName', '') or '',
        message_type=msg_type,
        text=text,
        media_url=media_url or '',
        status='received',
        evolution_id=evolution_id,
        timestamp=timestamp or timezone.now(),
        raw=payload_data,
    )
    return msg, True
