import csv
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Avg, Count, Q
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from authentication.whatsapp import clean_phone_number

from .models import Lead, LeadNote
from .serializers import LeadSerializer, LeadNoteSerializer
from .status_hooks import on_lead_status_changed
from audit.services import log_activity
from .import_utils import save_leads_from_dicts, parse_leads_upload
from .instagram_scraper import run_instagram_scraper
from .lead_export import build_lead_profile, lead_to_json, lead_to_markdown, slugify_filename
from .profile_picture_utils import (
    fetch_and_cache_profile_picture,
    read_avatar_bytes,
)


# ---------------------------------------------------------------------------
# Dashboard & Kanban
# ---------------------------------------------------------------------------

@login_required
def dashboard_view(request):
    user_leads = Lead.objects.filter(user=request.user)
    
    # Calculate statistics
    total_leads = user_leads.count()
    leads_by_status = dict(user_leads.values_list('status').annotate(count=Count('id')))
    
    novo = leads_by_status.get('novo', 0)
    contatado = leads_by_status.get('contatado', 0)
    negociacao = leads_by_status.get('negociacao', 0)
    fechado = leads_by_status.get('fechado', 0)
    finalizado = leads_by_status.get('finalizado', 0)
    perdido = leads_by_status.get('perdido', 0)
    
    avg_quality = user_leads.aggregate(avg=Avg('quality_score'))['avg'] or 0
    avg_quality = round(avg_quality, 1)
    
    google_maps_count = user_leads.filter(source='google_maps').count()
    instagram_count = user_leads.filter(source='instagram').count()
    
    # Calculate website percentage
    leads_with_site = user_leads.exclude(website='').exclude(website__isnull=True).count()
    site_percentage = round((leads_with_site / total_leads * 100), 1) if total_leads > 0 else 0
    
    # Calculate SVG dashoffset for source distribution chart (circumference = 314)
    maps_dashoffset = 314
    if total_leads > 0:
        maps_dashoffset = int(314 - (314 * (google_maps_count / total_leads)))
        
    # Recent leads
    recent_leads = user_leads[:6]
    
    context = {
        'total_leads': total_leads,
        'novo': novo,
        'contatado': contatado,
        'negociacao': negociacao,
        'fechado': fechado,
        'finalizado': finalizado,
        'perdido': perdido,
        'avg_quality': avg_quality,
        'google_maps_count': google_maps_count,
        'instagram_count': instagram_count,
        'site_percentage': site_percentage,
        'maps_dashoffset': maps_dashoffset,
        'recent_leads': recent_leads,
        'current_page': 'dashboard'
    }
    return render(request, 'leads/dashboard.html', context)

@login_required
def kanban_view(request):
    # Renders the main Kanban board
    context = {
        'current_page': 'kanban',
        'status_choices': Lead.STATUS_CHOICES
    }
    return render(request, 'leads/kanban.html', context)

@login_required
def instagram_scraper_view(request):
    if request.method == 'POST':
        niche = request.POST.get('niche', '').strip()
        location = request.POST.get('location', '').strip()
        limit = int(request.POST.get('limit', 10))
        only_verified = request.POST.get('only_verified') == 'on'
        only_with_bio_link = request.POST.get('only_with_bio_link') == 'on'
        
        if not niche:
            messages.error(request, "Por favor, informe pelo menos o nicho.")
            return render(request, 'leads/instagram_scraper.html')
            
        try:
            saved, skipped = run_instagram_scraper(
                user=request.user,
                niche=niche,
                location=location if location else None,
                limit=limit,
                only_verified=only_verified,
                only_with_bio_link=only_with_bio_link
            )
            log_activity(
                'instagram_scrape',
                f'Extração Instagram: {saved} salvos, {skipped} duplicados — nicho "{niche}".',
                user=request.user,
                metadata={'niche': niche, 'location': location, 'saved': saved, 'skipped': skipped},
                request=request,
            )
            messages.success(
                request, 
                f"Busca concluída! {saved} novos perfis importados. {skipped} duplicados ignorados."
            )
            return redirect('kanban')
        except Exception as e:
            messages.error(request, f"Erro no scraper do Instagram: {str(e)}")
            
    return render(request, 'leads/instagram_scraper.html', {'current_page': 'instagram_scraper'})

@login_required
def export_leads_view(request):
    export_format = request.GET.get('format', 'csv').lower()
    user_leads = Lead.objects.filter(user=request.user)
    
    # Filters
    status_filter = request.GET.get('status')
    source_filter = request.GET.get('source')
    search_query = request.GET.get('search')
    
    if status_filter:
        user_leads = user_leads.filter(status=status_filter)
    if source_filter:
        user_leads = user_leads.filter(source=source_filter)
    if search_query:
        user_leads = user_leads.filter(name__icontains=search_query) | user_leads.filter(category__icontains=search_query)
        
    if export_format == 'json':
        log_activity(
            'lead_export',
            f'Exportação JSON de {user_leads.count()} leads.',
            user=request.user,
            metadata={'format': 'json', 'count': user_leads.count()},
            request=request,
        )
        data = []
        for lead in user_leads:
            data.append({
                'name': lead.name,
                'category': lead.category,
                'city': lead.city,
                'phone_number': lead.phone_number,
                'normalized_phone': lead.normalized_phone,
                'website': lead.website,
                'instagram': lead.instagram,
                'facebook': lead.facebook,
                'bio': lead.bio,
                'address': lead.address,
                'rating': lead.rating,
                'source': lead.source,
                'status': lead.status,
                'quality_score': lead.quality_score,
                'created_at': lead.created_at.isoformat()
            })
        response = HttpResponse(json.dumps(data, indent=2, ensure_ascii=False), content_type='application/json')
        response['Content-Disposition'] = 'attachment; filename="leads_nuviie.json"'
        return response
        
    else:  # Default CSV
        log_activity(
            'lead_export',
            f'Exportação CSV de {user_leads.count()} leads.',
            user=request.user,
            metadata={'format': 'csv', 'count': user_leads.count()},
            request=request,
        )
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="leads_nuviie.csv"'
        
        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Nome da Empresa', 'Nicho/Categoria', 'Cidade', 'Telefone', 'WhatsApp Normalizado',
            'Website', 'Instagram', 'Facebook', 'Bio/Descrição', 'Endereço', 
            'Avaliação', 'Origem', 'Status', 'Pontuação de Qualidade', 'Data de Captura'
        ])
        
        for lead in user_leads:
            writer.writerow([
                lead.name, lead.category, lead.city, lead.phone_number, lead.normalized_phone,
                lead.website, lead.instagram, lead.facebook, lead.bio, lead.address,
                lead.rating, lead.get_source_display(), lead.get_status_display(), lead.quality_score,
                lead.created_at.strftime('%d/%m/%Y %H:%M')
            ])
            
        return response


# --- DRF API VIEWSETS ---

class LeadViewSet(viewsets.ModelViewSet):
    serializer_class = LeadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Return only the user's leads
        queryset = Lead.objects.filter(user=self.request.user)
        
        # Apply Query Filters (for real-time server-side tables)
        status_param = self.request.query_params.get('status')
        source_param = self.request.query_params.get('source')
        search_param = self.request.query_params.get('search')
        has_site_param = self.request.query_params.get('has_site')
        ordering_param = self.request.query_params.get('ordering')
        
        if status_param:
            queryset = queryset.filter(status=status_param)
        if source_param:
            queryset = queryset.filter(source=source_param)
        if search_param:
            queryset = queryset.filter(
                Q(name__icontains=search_param) |
                Q(category__icontains=search_param) |
                Q(city__icontains=search_param)
            )
        if has_site_param:
            if has_site_param == 'true':
                queryset = queryset.exclude(website='').exclude(website__isnull=True)
            elif has_site_param == 'false':
                queryset = queryset.filter(Q(website='') | Q(website__isnull=True))
                
        allowed_orderings = {
            '-quality_score', 'quality_score',
            '-created_at', 'created_at',
        }
        if ordering_param and ordering_param in allowed_orderings:
            queryset = queryset.order_by(ordering_param)
        else:
            queryset = queryset.order_by('-created_at')

        return queryset

    def perform_create(self, serializer):
        lead = serializer.save(user=self.request.user)
        LeadNote.objects.create(
            lead=lead,
            user=self.request.user,
            note="Lead criado manualmente no sistema.",
            action_type='creation'
        )
        log_activity(
            'lead_create',
            f'Lead criado: {lead.name}',
            user=self.request.user,
            entity_type='lead',
            entity_id=lead.pk,
            request=self.request,
        )

    def perform_destroy(self, instance):
        name = instance.name
        pk = instance.pk
        instance.delete()
        log_activity(
            'lead_delete',
            f'Lead excluído: {name}',
            user=self.request.user,
            entity_type='lead',
            entity_id=pk,
            request=self.request,
        )

    def perform_update(self, serializer):
        old_lead = self.get_object()
        old_status = old_lead.status
        old_name = old_lead.name
        old_phone = old_lead.phone_number
        
        lead = serializer.save()
        
        # Detect what changed to write log
        changes = []
        if old_status != lead.status:
            changes.append(f"Status alterado de '{old_lead.get_status_display()}' para '{lead.get_status_display()}'")
            LeadNote.objects.create(
                lead=lead,
                user=self.request.user,
                note=f"Status alterado de '{old_lead.get_status_display()}' para '{lead.get_status_display()}'",
                action_type='status_change'
            )
            on_lead_status_changed(lead, old_status, lead.status, self.request.user)
        
        # Standard edit log
        if old_name != lead.name or old_phone != lead.phone_number:
            LeadNote.objects.create(
                lead=lead,
                user=self.request.user,
                note="Dados cadastrais atualizados.",
                action_type='edit'
            )

    @action(detail=True, methods=['patch'], url_path='update-status')
    def update_status(self, request, pk=None):
        lead = self.get_object()
        new_status = request.data.get('status')
        
        valid_statuses = [choice[0] for choice in Lead.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return Response({'error': 'Status inválido'}, status=status.HTTP_400_BAD_REQUEST)
            
        old_status_display = lead.get_status_display()
        old_status = lead.status
        lead.status = new_status
        lead.save()
        
        LeadNote.objects.create(
            lead=lead,
            user=request.user,
            note=f"Status arrastado de '{old_status_display}' para '{lead.get_status_display()}' no Kanban.",
            action_type='status_change'
        )
        on_lead_status_changed(lead, old_status, new_status, request.user)
        
        return Response({
            'success': True,
            'new_status': lead.status,
            'status_display': lead.get_status_display(),
            'deadline_urgency': lead.deadline_urgency(),
            'days_until_deadline': lead.days_until_deadline(),
        })

    @action(detail=True, methods=['post'], url_path='add-note')
    def add_note(self, request, pk=None):
        lead = self.get_object()
        note_text = request.data.get('note', '').strip()
        
        if not note_text:
            return Response({'error': 'O texto da nota é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)
            
        note = LeadNote.objects.create(
            lead=lead,
            user=request.user,
            note=note_text,
            action_type='note'
        )
        
        return Response(LeadNoteSerializer(note).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='export')
    def export_lead(self, request, pk=None):
        lead = self.get_object()
        fmt = (request.query_params.get('file_type') or request.query_params.get('format') or 'md').lower()
        profile = build_lead_profile(lead)

        if fmt == 'json':
            content = lead_to_json(profile)
            filename = f'{slugify_filename(lead.name)}.json'
            content_type = 'application/json; charset=utf-8'
        elif fmt == 'md':
            content = lead_to_markdown(profile)
            filename = f'{slugify_filename(lead.name)}.md'
            content_type = 'text/markdown; charset=utf-8'
        else:
            return Response({'error': 'Formato inválido. Use file_type=md ou file_type=json.'}, status=status.HTTP_400_BAD_REQUEST)

        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @action(detail=True, methods=['post'], url_path='extract-palette')
    def extract_palette(self, request, pk=None):
        from .palette_utils import extract_and_store_palette

        lead = self.get_object()
        image_url = (request.data.get('image_url') or '').strip() or None
        try:
            palette_data = extract_and_store_palette(lead, image_url=image_url)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({'error': f'Falha ao extrair paleta: {exc}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        lead.refresh_from_db()
        return Response({
            'color_palette': palette_data,
            'lead': LeadSerializer(lead, context={'request': request}).data,
        })

    @action(detail=True, methods=['get', 'put', 'post', 'patch', 'delete'], url_path='color-palette')
    def color_palette_crud(self, request, pk=None):
        from .palette_utils import (
            add_palette_color,
            clear_palette,
            delete_palette_color,
            get_stored_palette,
            save_palette,
            update_palette_color,
        )

        lead = self.get_object()

        if request.method == 'GET':
            palette = get_stored_palette(lead)
            return Response({'color_palette': palette})

        try:
            if request.method == 'PUT':
                colors = request.data.get('colors')
                source = (request.data.get('source') or 'manual').strip() or 'manual'
                palette_data = save_palette(lead, colors, source=source)
            elif request.method == 'POST':
                hex_value = request.data.get('hex') or request.data.get('color')
                if not hex_value and request.data.get('colors'):
                    palette_data = save_palette(lead, request.data['colors'], source='manual')
                elif hex_value:
                    palette_data = add_palette_color(lead, hex_value)
                else:
                    return Response({'error': 'Informe hex ou colors.'}, status=status.HTTP_400_BAD_REQUEST)
            elif request.method == 'PATCH':
                index = request.data.get('index')
                hex_value = request.data.get('hex') or request.data.get('color')
                if index is None or hex_value is None:
                    return Response({'error': 'Informe index e hex.'}, status=status.HTTP_400_BAD_REQUEST)
                palette_data = update_palette_color(lead, int(index), hex_value)
            elif request.method == 'DELETE':
                index_raw = request.query_params.get('index')
                if index_raw is not None and index_raw != '':
                    palette_data = delete_palette_color(lead, int(index_raw))
                else:
                    clear_palette(lead)
                    palette_data = None
            else:
                return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({'error': f'Falha na paleta: {exc}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        lead.refresh_from_db()
        return Response({
            'color_palette': palette_data,
            'lead': LeadSerializer(lead, context={'request': request}).data,
        })

    @action(detail=True, methods=['get'], url_path='avatar')
    def avatar(self, request, pk=None):
        lead = self.get_object()
        cached = read_avatar_bytes(lead)
        if cached:
            content, content_type = cached
            return HttpResponse(content, content_type=content_type)

        if lead.profile_picture_url:
            local_url = fetch_and_cache_profile_picture(lead, lead.profile_picture_url)
            if local_url:
                lead.profile_picture_url = local_url
                lead.save(update_fields=['profile_picture_url'])
                cached = read_avatar_bytes(lead)
                if cached:
                    content, content_type = cached
                    return HttpResponse(content, content_type=content_type)

        return Response(status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        if not isinstance(ids, list) or not ids:
            return Response({'error': 'Informe uma lista de IDs.'}, status=status.HTTP_400_BAD_REQUEST)
        qs = Lead.objects.filter(user=request.user, id__in=ids)
        count = qs.count()
        names = list(qs.values_list('name', flat=True)[:5])
        qs.delete()
        log_activity(
            'lead_bulk_delete',
            f'{count} leads excluídos em massa.',
            user=request.user,
            metadata={'count': count, 'sample': names},
            request=request,
        )
        return Response({'deleted': count})

    @action(detail=False, methods=['post'], url_path='delete-all')
    def delete_all(self, request):
        if not request.data.get('confirm'):
            return Response({'error': 'Confirmação necessária.'}, status=status.HTTP_400_BAD_REQUEST)
        qs = Lead.objects.filter(user=request.user)
        count = qs.count()
        qs.delete()
        log_activity(
            'lead_delete_all',
            f'Todos os leads excluídos ({count}).',
            user=request.user,
            metadata={'count': count},
            request=request,
        )
        return Response({'deleted': count})


# ---------------------------------------------------------------------------
# Extensão Chrome — bulk import via token
# ---------------------------------------------------------------------------

def _extension_import_user():
    username = getattr(settings, 'NUVIIE_EXTENSION_USER', '') or 'admin'
    User = get_user_model()
    return User.objects.filter(username=username).first()


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def bulk_import_leads_view(request):
    expected = getattr(settings, 'NUVIIE_EXTENSION_TOKEN', '')
    token = request.headers.get('X-Nuviie-Token', '')
    if not expected or token != expected:
        return Response({'error': 'Token inválido ou não configurado.'}, status=status.HTTP_401_UNAUTHORIZED)

    user = _extension_import_user()
    if not user:
        return Response(
            {'error': f'Usuário NUVIIE_EXTENSION_USER não encontrado.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    leads = request.data.get('leads', [])
    if not isinstance(leads, list):
        return Response({'error': 'Campo "leads" deve ser uma lista.'}, status=status.HTTP_400_BAD_REQUEST)

    city = (request.data.get('city') or '').strip()
    normalized = []
    for item in leads:
        if not isinstance(item, dict):
            continue
        lead = dict(item)
        if city and not lead.get('city'):
            lead['city'] = city
        if not lead.get('source'):
            lead['source'] = 'google_maps'
        normalized.append(lead)

    saved, skipped, updated, skipped_reasons = save_leads_from_dicts(user, normalized)
    log_activity(
        'lead_import',
        f'Importação via extensão: {saved} salvos, {updated} atualizados, {skipped} ignorados.',
        user=user,
        metadata={'saved': saved, 'updated': updated, 'skipped': skipped, 'source': 'extension'},
        request=request,
    )
    return Response({
        'saved': saved,
        'updated': updated,
        'skipped': skipped,
        'skipped_reasons': skipped_reasons,
        'errors': [],
    })


@login_required
def import_leads_view(request):
    if request.method == 'POST':
        upload = request.FILES.get('file')
        if not upload:
            messages.error(request, 'Selecione um arquivo JSON ou CSV.')
            return render(request, 'leads/import_leads.html', {'current_page': 'import_leads'})

        try:
            content = upload.read().decode('utf-8-sig')
            leads_data = parse_leads_upload(content, upload.name)
            saved, skipped, _updated, _reasons = save_leads_from_dicts(request.user, leads_data)
            log_activity(
                'lead_import',
                f'Importação de arquivo: {saved} salvos, {skipped} duplicados.',
                user=request.user,
                metadata={'saved': saved, 'skipped': skipped, 'filename': upload.name},
                request=request,
            )
            messages.success(
                request,
                f'Importação concluída! {saved} novos leads salvos. {skipped} duplicados ignorados.',
            )
            return redirect('kanban')
        except (ValueError, json.JSONDecodeError) as e:
            messages.error(request, f'Erro ao ler arquivo: {e}')
        except Exception as e:
            messages.error(request, f'Erro na importação: {e}')

    return render(request, 'leads/import_leads.html', {'current_page': 'import_leads'})