import csv
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Avg, Count
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from authentication.whatsapp import clean_phone_number

from .models import Lead, LeadNote
from .serializers import LeadSerializer, LeadNoteSerializer
from .scraper import run_google_maps_scraper, run_instagram_scraper


# ---------------------------------------------------------------------------
# Browser Preview — abre URL com Playwright e retorna screenshot base64
# ---------------------------------------------------------------------------

@login_required
def browser_preview_view(request):
    """
    GET /leads/preview/?url=<encoded_url>
    Executa preview_runner.py como subprocesso, tira screenshot com Playwright
    e retorna JSON: { 'image': 'data:image/png;base64,...' } ou { 'error': '...' }
    """
    import base64 as _b64
    import json as _json
    import subprocess
    import sys as _sys
    from pathlib import Path

    url = request.GET.get('url', '').strip()
    if not url:
        return JsonResponse({'error': 'URL não fornecida'}, status=400)

    if not url.startswith(('http://', 'https://')):
        return JsonResponse({'error': 'URL inválida'}, status=400)

    # Monta args para o runner
    args = {
        'url': url,
        'viewport_width': 1280,
        'timeout_ms': 25000,
    }
    args_b64 = _b64.b64encode(_json.dumps(args).encode('utf-8')).decode('ascii')

    # Localiza preview_runner.py (na mesma pasta de scraper_runner.py)
    runner_path = Path(__file__).resolve().parent / 'preview_runner.py'
    if not runner_path.exists():
        return JsonResponse({'error': f'preview_runner.py não encontrado em {runner_path}'}, status=500)

    # Repassa PLAYWRIGHT_BROWSERS_PATH se definido
    env = dict(__import__('os').environ)
    pw_path_env = env.get('PLAYWRIGHT_BROWSERS_PATH')
    if not pw_path_env:
        # tenta detectar automaticamente
        import pathlib
        home = pathlib.Path.home()
        for candidate in [
            home / 'AppData' / 'Local' / 'ms-playwright',
            home / '.cache' / 'ms-playwright',
        ]:
            if candidate.exists() and list(candidate.glob('firefox-*')):
                env['PLAYWRIGHT_BROWSERS_PATH'] = str(candidate)
                break

    try:
        proc = subprocess.run(
            [_sys.executable, str(runner_path), args_b64],
            capture_output=True,
            text=True,
            timeout=45,
            env=env,
            cwd=str(runner_path.parent),
        )
    except subprocess.TimeoutExpired:
        return JsonResponse({'error': 'Timeout ao carregar a página (45s)'}, status=504)
    except Exception as e:
        return JsonResponse({'error': f'Erro ao iniciar subprocesso: {e}'}, status=500)

    # Procura o marcador no stdout
    stdout = proc.stdout or ''
    for line in stdout.splitlines():
        if line.startswith('__PREVIEW_RESULT__'):
            img_b64 = line[len('__PREVIEW_RESULT__'):]
            return JsonResponse({
                'image': f'data:image/png;base64,{img_b64}'
            })
        if line.startswith('__PREVIEW_ERROR__'):
            error_msg = line[len('__PREVIEW_ERROR__'):]
            return JsonResponse({'error': error_msg}, status=502)

    # Nenhum marcador encontrado
    stderr_snippet = (proc.stderr or '')[-800:]
    return JsonResponse({
        'error': 'Nenhum resultado do runner',
        'stderr': stderr_snippet,
    }, status=502)


@login_required
def open_browser_view(request):
    """
    GET /leads/open-browser/?url=<encoded_url>

    Abre o Firefox real do Playwright na URL solicitada via subprocess.Popen.
    Retorna JSON: { 'ok': true } ou { 'error': '...' }

    Lógica:
    1. Localiza o executável do Firefox instalado pelo Playwright
    2. Abre com subprocess.Popen (não-bloqueante) passando a URL
    3. Retorna imediatamente — a janela Firefox aparece para o usuário
    """
    import subprocess
    import pathlib
    import os as _os

    url = request.GET.get('url', '').strip()
    if not url:
        return JsonResponse({'error': 'URL não fornecida'}, status=400)

    if not url.startswith(('http://', 'https://')):
        return JsonResponse({'error': 'URL inválida — apenas http/https'}, status=400)

    # ── Encontra o Firefox do Playwright ─────────────────────────────────────
    def _find_firefox_bin() -> str | None:
        """Localiza o executável do Firefox instalado pelo Playwright."""
        import sys as _sys

        home = pathlib.Path.home()
        username = _os.environ.get('USERNAME') or _os.environ.get('USER') or ''

        # Diretórios candidatos do ms-playwright
        pw_env = _os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '')
        candidates_dirs = [
            pathlib.Path(pw_env) if pw_env else None,
            home / 'AppData' / 'Local' / 'ms-playwright',   # Windows
            home / '.cache' / 'ms-playwright',               # Linux/Mac
            pathlib.Path('/root/.cache/ms-playwright'),
        ]
        if username:
            candidates_dirs.append(pathlib.Path(f'/home/{username}/.cache/ms-playwright'))

        for base in candidates_dirs:
            if not base or not base.exists():
                continue

            firefox_dirs = sorted(base.glob('firefox-*'), reverse=True)
            for ff_dir in firefox_dirs:
                # Windows: firefox.exe dentro de firefox\
                for exe_path in [
                    ff_dir / 'firefox' / 'firefox.exe',       # Windows
                    ff_dir / 'firefox' / 'firefox',            # Linux
                    ff_dir / 'firefox.exe',                    # Windows alt
                    ff_dir / 'firefox',                        # Linux alt
                    ff_dir / 'Firefox.app' / 'Contents' / 'MacOS' / 'firefox',  # Mac
                ]:
                    if exe_path.exists():
                        return str(exe_path)

        return None

    firefox_bin = _find_firefox_bin()

    if not firefox_bin:
        # Fallback: tenta o Firefox do sistema operacional
        import shutil
        for candidate in ('firefox', 'firefox-esr', 'firefox-bin'):
            found = shutil.which(candidate)
            if found:
                firefox_bin = found
                break

    if not firefox_bin:
        return JsonResponse({
            'error': (
                'Firefox não encontrado. '
                'Execute "playwright install firefox" para instalar, '
                'ou instale o Firefox no sistema.'
            )
        }, status=500)

    # ── Abre o Firefox com a URL ──────────────────────────────────────────────
    try:
        env = dict(_os.environ)

        # Define PLAYWRIGHT_BROWSERS_PATH se não estiver definido
        pw_path = env.get('PLAYWRIGHT_BROWSERS_PATH')
        if not pw_path:
            home = pathlib.Path.home()
            for candidate in [
                home / 'AppData' / 'Local' / 'ms-playwright',
                home / '.cache' / 'ms-playwright',
            ]:
                if candidate.exists() and list(candidate.glob('firefox-*')):
                    env['PLAYWRIGHT_BROWSERS_PATH'] = str(candidate)
                    break

        # Abre Firefox de forma não-bloqueante (Popen, não run/wait)
        proc = subprocess.Popen(
            [firefox_bin, '--new-window', url],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # No Windows: não abre janela de console extra
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )

        return JsonResponse({
            'ok': True,
            'firefox_bin': firefox_bin,
            'pid': proc.pid,
        })

    except Exception as e:
        return JsonResponse({'error': f'Erro ao abrir Firefox: {e}'}, status=500)


# --- STANDARD TEMPLATE VIEWS ---

@login_required
def dashboard_view(request):
    user_leads = Lead.objects.filter(user=request.user)
    
    # Calculate statistics
    total_leads = user_leads.count()
    leads_by_status = dict(user_leads.values_list('status').annotate(count=Count('id')))
    
    novo = leads_by_status.get('novo', 0)
    contatado = leads_by_status.get('contatado', 0)
    negociacao = leads_by_status.get('negociacao', 0)
    retornou = leads_by_status.get('retornou', 0)
    fechado = leads_by_status.get('fechado', 0)
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
        'retornou': retornou,
        'fechado': fechado,
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
def maps_scraper_view(request):
    if request.method == 'POST':
        city = request.POST.get('city', '').strip()
        niche = request.POST.get('niche', '').strip()
        limit = int(request.POST.get('limit', 10))
        only_without_website = request.POST.get('only_without_website') == 'on'
        only_with_instagram = request.POST.get('only_with_instagram') == 'on'
        only_with_facebook = request.POST.get('only_with_facebook') == 'on'

        min_rating_raw = request.POST.get('min_rating', '').strip()
        min_rating = float(min_rating_raw) if min_rating_raw else None

        min_reviews_raw = request.POST.get('min_reviews', '').strip()
        min_reviews = int(min_reviews_raw) if min_reviews_raw else None

        if not city or not niche:
            messages.error(request, "Por favor, preencha a cidade e o nicho.")
            return render(request, 'leads/maps_scraper.html')

        try:
            saved, skipped = run_google_maps_scraper(
                user=request.user,
                city=city,
                niche=niche,
                limit=limit,
                only_without_website=only_without_website,
                min_rating=min_rating,
                min_reviews=min_reviews,
                only_with_instagram=only_with_instagram,
                only_with_facebook=only_with_facebook,
            )
            messages.success(
                request, 
                f"Scraping concluído! {saved} novos leads importados. {skipped} duplicados ignorados."
            )
            return redirect('kanban')
        except Exception as e:
            messages.error(request, f"Erro na extração: {str(e)}")
            
    return render(request, 'leads/maps_scraper.html', {'current_page': 'maps_scraper'})

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
        
    else: # Default CSV
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
                models.Q(name__icontains=search_param) | 
                models.Q(category__icontains=search_param) |
                models.Q(city__icontains=search_param)
            )
        if has_site_param:
            if has_site_param == 'true':
                queryset = queryset.exclude(website='').exclude(website__isnull=True)
            elif has_site_param == 'false':
                queryset = queryset.filter(models.Q(website='') | models.Q(website__isnull=True))
                
        if ordering_param:
            queryset = queryset.order_by(ordering_param)
            
        return queryset

    def perform_create(self, serializer):
        lead = serializer.save(user=self.request.user)
        # Add system log
        LeadNote.objects.create(
            lead=lead,
            user=self.request.user,
            note="Lead criado manualmente no sistema.",
            action_type='creation'
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
        lead.status = new_status
        lead.save()
        
        LeadNote.objects.create(
            lead=lead,
            user=request.user,
            note=f"Status arrastado de '{old_status_display}' para '{lead.get_status_display()}' no Kanban.",
            action_type='status_change'
        )
        
        return Response({'success': True, 'new_status': lead.status, 'status_display': lead.get_status_display()})

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