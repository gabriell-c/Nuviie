"""
scraper.py — Nuviie Lead Scraper v12
====================================
Novidades v12 — EXTRAÇÃO MÁXIMA + GRID SCRAPING:

  NOVOS CAMPOS EXTRAÍDOS:
  - latitude / longitude: extraídos diretamente da URL canônica do Maps
    (@LAT,LNG,ZOOMz) e do HTML da página, sem geocoding externo.
  - cid: Customer ID numérico do Google (identificador único e permanente
    do lugar, extraído de data-cid, aria-label e URL).
  - kgmid: Knowledge Graph Machine ID (ex: /g/11bc6m7q3k), o identificador
    mais estável do Google — nunca é nulo quando disponível.
  - order_online / menu / reservations: links de pedido online, cardápio e
    reservas, extraídos dos botões de ação da ficha.
  - popular_times: horários de pico por dia da semana (quando disponível),
    com porcentagem de ocupação por hora — útil para vendas B2B.
  - coordinates: objeto {lat, lng} consolidado.

  GRID SCRAPING (inspirado em gosom/google-maps-scraper):
  - Novo parâmetro `grid_bbox`: "minLat,minLon,maxLat,maxLon" divide a área
    em células e executa uma busca por célula. Garante cobertura total de
    uma cidade/bairro sem perder negócios fora do centro.
  - Parâmetro `grid_cell_km`: tamanho da célula em km (padrão 1.0).
  - Deduplicação automática por CID/kgmid entre células.
  - Integra com o pipeline existente sem breaking changes.

  FAST MODE (inspirado em gosom/google-maps-scraper):
  - Parâmetro `fast_mode=True`: coleta até 21 resultados por query ordenados
    por distância, sem visitar cada ficha individualmente.
  - Útil para prospecção rápida quando detalhes completos não são necessários.
  - Retorna: nome, categoria, endereço, rating, review_count, lat/lng, maps_url.

  DEDUPLICAÇÃO EM TEMPO REAL:
  - Durante o scroll da lista de resultados, URLs já visitadas são descartadas
    imediatamente (seen_urls por CID ou base URL).
  - Entre requests paralelas, um lock asyncio garante que o mesmo lugar não
    seja processado duas vezes mesmo com _PARALLEL_TABS > 1.

  MELHORIAS NO JS_EXTRACT_ALL:
  - kgmid: extrai de <link rel="canonical">, window.APP_INITIALIZATION_STATE
    e padrões /g/ na URL.
  - cid: extrai de data-cid, URL, e window.__google_map_state__.
  - lat/lng: parse direto da URL @LAT,LNG,ZOOMz sem regex frágeis.
  - order_online: captura links "Fazer pedido", "Pedir online", iFood, etc.
  - menu: captura links de cardápio.
  - reservations: captura links de reserva (Google Reservations, OpenTable, etc.).
  - popular_times: extrai porcentagem de ocupação por hora de cada dia.

Novidades v11 mantidas:
  - Scroll multi-container, navegação pelas abas Sobre/Avaliações,
    horários com 2 períodos, Plus Code aprimorado, amenidades expandidas.

Novidades v5–v10 mantidas:
  - Screenshot de diagnóstico, logging estruturado, sessão persistente,
    consentimento robusto, subprocesso isolado, heartbeat, etc.

Dependências:
    pip install playwright beautifulsoup4 requests
    playwright install firefox
"""

import re
import asyncio
import time
import random
import logging
import urllib.parse
import os
import sys
import math

import requests
from bs4 import BeautifulSoup
from authentication.whatsapp import clean_phone_number
from .models import Lead

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# v12: Grid Scraping — helpers de geolocalização
# ---------------------------------------------------------------------------

def _bbox_to_grid(min_lat: float, min_lon: float, max_lat: float, max_lon: float,
                   cell_km: float = 1.0) -> list[tuple[float, float]]:
    """
    Divide uma bounding box em uma grade de pontos centrais separados por cell_km.
    Retorna lista de (lat, lon) representando o centro de cada célula.
    Inspirado em gosom/google-maps-scraper grid mode.
    """
    lat_step = cell_km / 111.0
    mid_lat = (min_lat + max_lat) / 2.0
    lon_step = cell_km / (111.0 * math.cos(math.radians(mid_lat)))

    points = []
    lat = min_lat + lat_step / 2
    while lat <= max_lat:
        lon = min_lon + lon_step / 2
        while lon <= max_lon:
            points.append((round(lat, 6), round(lon, 6)))
            lon += lon_step
        lat += lat_step

    logger.info(
        f"[Maps][Grid] bbox=({min_lat},{min_lon})→({max_lat},{max_lon}) "
        f"cell={cell_km}km → {len(points)} células"
    )
    return points


def _parse_bbox(bbox_str: str) -> tuple[float, float, float, float] | None:
    """Parseia 'minLat,minLon,maxLat,maxLon' → tuple de floats."""
    try:
        parts = [float(x.strip()) for x in bbox_str.split(',')]
        if len(parts) == 4:
            return tuple(parts)
    except (ValueError, AttributeError):
        pass
    logger.error(f"[Maps][Grid] bbox inválido: {bbox_str!r} — use 'minLat,minLon,maxLat,maxLon'")
    return None


def _extract_lat_lng_from_url(url: str) -> tuple[float | None, float | None]:
    """
    Extrai latitude e longitude da URL canônica do Google Maps.
    Suporta formatos:
      - @-23.5489,46.6388,15z  (mais comum)
      - !3d-23.5489!4d-46.6388  (formato alternativo)
      - ll=-23.5489,-46.6388   (formato legado)
    """
    if not url:
        return None, None
    m = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+),\d+', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'll=(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None


def _extract_cid_from_url(url: str) -> str | None:
    """Extrai o CID (Customer ID) numérico de uma URL do Google Maps."""
    if not url:
        return None
    m = re.search(r'[?&]cid=(\d+)', url)
    if m:
        return m.group(1)
    return None

# ---------------------------------------------------------------------------
# DDD por cidade
# ---------------------------------------------------------------------------
CITY_DDDS = {
    'ribeirão preto': '16', 'ribeirao preto': '16',
    'são paulo': '11', 'sao paulo': '11', 'sp': '11',
    'campinas': '19', 'santos': '13', 'sorocaba': '15',
    'são josé dos campos': '12', 'sao jose dos campos': '12',
    'rio de janeiro': '21', 'rj': '21', 'niterói': '21', 'niteroi': '21',
    'belo horizonte': '31', 'bh': '31', 'uberlândia': '34', 'juiz de fora': '32',
    'curitiba': '41', 'londrina': '43', 'maringá': '44',
    'porto alegre': '51', 'poa': '51',
    'salvador': '71', 'feira de santana': '75',
    'fortaleza': '85', 'recife': '81',
    'brasília': '61', 'brasilia': '61', 'df': '61',
    'goiânia': '62', 'goiania': '62',
    'manaus': '92', 'belém': '91', 'belem': '91',
    'natal': '84', 'maceió': '82', 'maceio': '82',
    'joão pessoa': '83', 'joao pessoa': '83',
    'teresina': '86', 'campo grande': '67', 'cuiabá': '65',
    'florianópolis': '48', 'florianopolis': '48', 'joinville': '47',
}

def get_ddd(city: str) -> str:
    c = city.lower().strip()
    for k, v in CITY_DDDS.items():
        if k in c:
            return v
    return ''

def normalize_phone(phone: str) -> str | None:
    """Normaliza para formato internacional 55DDXXXXXXXXX."""
    digits = re.sub(r'\D', '', phone)
    if not digits:
        return None
    if digits.startswith('55') and len(digits) > 12:
        digits = digits[2:]
    if len(digits) < 8:
        return None
    if len(digits) <= 11:
        digits = '55' + digits
    return digits


# ---------------------------------------------------------------------------
# ✅ Detecção inteligente do tipo real do link "site"
# ---------------------------------------------------------------------------

_SITE_TYPE_PATTERNS = [
    ('instagram',    re.compile(r'instagram\.com/', re.I)),
    ('whatsapp',     re.compile(r'(?:wa\.me|api\.whatsapp\.com|chat\.whatsapp\.com)', re.I)),
    ('facebook',     re.compile(r'(?:facebook\.com|fb\.com|fb\.me)/', re.I)),
    ('youtube',      re.compile(r'youtube\.com/', re.I)),
    ('linktree',     re.compile(r'(?:linktr\.ee|linkinbio\.|bio\.site|beacons\.ai|linky\.bio|milkshake\.app)', re.I)),
    ('other_social', re.compile(r'(?:tiktok\.com|twitter\.com|x\.com|snapchat\.com|pinterest\.com|threads\.net)', re.I)),
]

def detect_website_type(url: str | None) -> str:
    if not url:
        return 'website'
    for type_name, pattern in _SITE_TYPE_PATTERNS:
        if pattern.search(url):
            return type_name
    return 'website'


def _resolve_social_from_website(url: str | None, data: dict) -> None:
    if not url:
        return
    dtype = detect_website_type(url)
    data['website_detected_type'] = dtype

    if dtype == 'instagram':
        m = re.search(r'instagram\.com/([A-Za-z0-9._]{1,50})/?', url, re.I)
        if m and not data.get('instagram'):
            data['instagram'] = f"@{m.group(1).rstrip('/')}"
        data['website'] = None

    elif dtype == 'whatsapp':
        m = re.search(r'(?:wa\.me|phone=|phone%3D)[\+/]?(\d{10,15})', url)
        if m and not data.get('normalized_phone'):
            data['normalized_phone'] = m.group(1)
        data['website'] = None

    elif dtype == 'facebook':
        if not data.get('facebook'):
            data['facebook'] = url
        data['website'] = None

    elif dtype == 'youtube':
        if not data.get('youtube'):
            data['youtube'] = url
        data['website'] = None

    elif dtype in ('linktree', 'other_social'):
        data['website'] = url


# ---------------------------------------------------------------------------
# Playwright — scraper principal do Google Maps
# ---------------------------------------------------------------------------

_PARALLEL_TABS = 4


async def _launch_browser_async(p):
    return await p.firefox.launch(
        headless=True,
        firefox_user_prefs={
            'intl.accept_languages': 'pt-BR, pt, en-US, en',
            'general.useragent.override': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) '
                'Gecko/20100101 Firefox/125.0'
            ),
            # Desabilita detecção de automação do Firefox
            'dom.webdriver.enabled': False,
            'useAutomationExtension': False,
            # Melhora compatibilidade com Google Maps
            'privacy.resistFingerprinting': False,
            'geo.enabled': False,
        }
    )

async def _new_context_async(browser, **extra_kwargs):
    context = await browser.new_context(
        locale='pt-BR',
        timezone_id='America/Sao_Paulo',
        user_agent=(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) '
            'Gecko/20100101 Firefox/125.0'
        ),
        viewport={'width': 1366, 'height': 768},
        **extra_kwargs,
    )
    # Firefox não precisa do patch de webdriver/chrome — ele já passa
    # nas verificações do Google Maps sem scripts adicionais.
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['pt-BR', 'pt', 'en-US', 'en'],
        });
    """)
    return context


# ── Sync wrappers mantidos para compatibilidade ───────────────────────────────
def _launch_browser(p):
    raise RuntimeError("Use _launch_browser_async com async_playwright")

def _new_context(browser):
    raise RuntimeError("Use _new_context_async com async_playwright")


# ---------------------------------------------------------------------------
# ✅ v5: Helpers de diagnóstico
# ---------------------------------------------------------------------------

def _get_screenshot_dir() -> str:
    """
    Retorna o diretório onde os screenshots serão salvos.
    Prioridade:
      1) Variável de ambiente NUVIIE_SCREENSHOT_DIR
      2) Pasta tmp/ relativa ao projeto (detectada via __file__)
      3) Fallback: /tmp (Linux) ou %TEMP% (Windows)
    """
    import pathlib
    # 1) env var explícita
    env_dir = os.environ.get('NUVIIE_SCREENSHOT_DIR')
    if env_dir:
        p = pathlib.Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return str(p)
    # 2) pasta tmp/ no root do projeto (dois níveis acima de leads/scraper.py)
    try:
        project_root = pathlib.Path(__file__).resolve().parent.parent
        tmp_dir = project_root / 'tmp'
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return str(tmp_dir)
    except Exception:
        pass
    # 3) fallback
    fallback = os.environ.get('TEMP') or os.environ.get('TMP') or '/tmp'
    return fallback


async def _save_debug_screenshot(page, label: str) -> str | None:
    """Salva screenshot para diagnóstico e retorna o caminho."""
    import time as _time
    try:
        ts = int(_time.time())
        screenshot_dir = _get_screenshot_dir()
        path = os.path.join(screenshot_dir, f"maps_debug_{label}_{ts}.png")
        await page.screenshot(path=path, full_page=True)
        logger.info(f"[Maps:diag] Screenshot salvo: {path}")
        return path
    except Exception as e:
        logger.error(f"[Maps:diag] Falha ao salvar screenshot: {e}")
        return None


async def _log_page_state(page, label: str, html_chars: int = 5000) -> None:
    """Loga URL atual, título e snippet do HTML para diagnóstico."""
    try:
        current_url = page.url
        page_title = await page.title()
        logger.error(f"[Maps:diag:{label}] URL atual  : {current_url}")
        logger.error(f"[Maps:diag:{label}] Título     : {page_title}")

        # Detecta CAPTCHA
        title_lower = page_title.lower()
        if any(w in title_lower for w in ('captcha', 'unusual traffic', 'robot', 'verify')):
            logger.error(f"[Maps:diag:{label}] ⚠️  CAPTCHA / bloqueio detectado no título!")

        # Detecta consent wall
        if any(w in title_lower for w in ('consent', 'consentimento', 'privacy', 'privacidade')):
            logger.error(f"[Maps:diag:{label}] ⚠️  Tela de consentimento detectada no título!")

        # Snippet do HTML
        html_snippet = await page.evaluate(
            f"document.body ? document.body.innerHTML.slice(0, {html_chars}) : '<no body>'"
        )
        logger.error(f"[Maps:diag:{label}] HTML snippet ({html_chars} chars):\n{html_snippet}")

    except Exception as e:
        logger.error(f"[Maps:diag:{label}] Falha ao logar estado: {e}")


def _check_system_deps() -> list[str]:
    """
    Verifica dependências do sistema necessárias para o Playwright headless.
    Retorna lista de avisos (vazia = tudo OK).
    NÃO usa 'playwright install --check' pois o flag não existe em versões antigas.
    """
    warnings_list = []

    # 1. Verifica se o pacote playwright está importável
    try:
        import playwright as _pw
        version = getattr(_pw, '__version__', 'desconhecida')
        logger.info(f"[Maps:dep] playwright instalado — versão: {version}")
    except ImportError:
        warnings_list.append(
            "Playwright NÃO instalado. Execute: pip install playwright && playwright install firefox"
        )
        return warnings_list  # sem playwright, não adianta verificar mais

    # 2. Verifica se o Firefox existe no disco (sem iniciar playwright completo)
    try:
        import pathlib
        home = pathlib.Path.home()
        user = os.environ.get('USER', '')
        candidates = [
            home / '.cache' / 'ms-playwright',
            home / 'AppData' / 'Local' / 'ms-playwright',
            pathlib.Path('/root/.cache/ms-playwright'),
            pathlib.Path('/tmp/ms-playwright'),
        ]
        if user:
            candidates.append(pathlib.Path(f'/home/{user}/.cache/ms-playwright'))

        found_dir = next((c for c in candidates if c.exists()), None)
        if found_dir:
            firefox_dirs = list(found_dir.glob('firefox-*'))
            if firefox_dirs:
                logger.info(f"[Maps:dep] Firefox OK: {found_dir}/{firefox_dirs[0].name}")
            else:
                warnings_list.append(
                    f"Firefox NÃO encontrado em {found_dir}. "
                    "Execute: playwright install firefox"
                )
        else:
            warnings_list.append(
                "Diretório ms-playwright não encontrado. "
                "Execute: playwright install firefox"
            )
    except Exception as e:
        warnings_list.append(f"Erro ao verificar Firefox: {e}")

    # 3. DISPLAY em Linux (apenas informativo para headless moderno)
    if os.name != 'nt' and not os.environ.get('DISPLAY'):
        logger.info(
            "[Maps:dep] DISPLAY não definido — OK para headless moderno, "
            "mas pode causar problema em servidores antigos."
        )

    return warnings_list


# ---------------------------------------------------------------------------
# ✅ v5: Consentimento robusto
# ---------------------------------------------------------------------------

async def _handle_consent(page) -> bool:
    """
    Tenta aceitar qualquer tela de consentimento/cookies do Google.
    Cobre variações por idioma, região e versão do Google.
    Retorna True se clicou em algum botão.
    """
    # Seletores em ordem de especificidade: do mais específico ao mais genérico
    consent_selectors = [
        # Textos exatos em pt-BR
        'button:has-text("Aceitar tudo")',
        'button:has-text("Aceitar todos")',
        'button:has-text("Concordar")',
        'button:has-text("Aceitar")',
        # Inglês
        'button:has-text("Accept all")',
        'button:has-text("I agree")',
        'button:has-text("Agree")',
        'button:has-text("Accept")',
        # Espanhol / outros
        'button:has-text("Aceptar todo")',
        'button:has-text("Aceptar")',
        # aria-label
        'button[aria-label*="Aceitar"]',
        'button[aria-label*="Accept"]',
        'button[aria-label*="Concordar"]',
        # Formulário de consentimento — botão de confirmação (geralmente o último)
        'form[action*="consent"] button:last-of-type',
        'form[action*="sconsent"] button',
        # ID específico do consent do Google
        '#L2AGLb',   # botão "Accept all" da tela de consentimento EU
        'button.tHlp8d',  # variação conhecida
    ]

    for sel in consent_selectors:
        try:
            btn = await page.query_selector(sel)
            if btn:
                is_visible = await btn.is_visible()
                if is_visible:
                    await btn.click()
                    await asyncio.sleep(1.5)
                    logger.info(f"[Maps] Consentimento aceito via seletor: {sel!r}")
                    return True
        except Exception:
            continue

    # Fallback: tenta iframe de consentimento
    try:
        frames = page.frames
        for frame in frames:
            if 'consent' in (frame.url or '').lower():
                for sel in consent_selectors[:8]:
                    try:
                        btn = await frame.query_selector(sel)
                        if btn and await btn.is_visible():
                            await btn.click()
                            await asyncio.sleep(1.5)
                            logger.info(f"[Maps] Consentimento aceito via iframe: {sel!r}")
                            return True
                    except Exception:
                        continue
    except Exception:
        pass

    return False


# ---------------------------------------------------------------------------
# ✅ v7: _pw_diag — bypass do logging do Django no subprocesso
# ---------------------------------------------------------------------------

def _pw_diag(msg: str, level: str = 'info') -> None:
    """
    Imprime diagnóstico DIRETO no stderr do subprocesso via print().
    Isso garante que os logs apareçam mesmo quando o Django suprime
    loggers filhos (ex: 'leads.scraper') no LOGGING config do settings.py.
    Os logs chegam ao processo pai como [Maps:worker] no terminal Django.
    """
    import sys as _sys
    ts = __import__('time').strftime('%H:%M:%S')
    prefix = {'error': 'ERROR', 'warning': 'WARN ', 'info': 'INFO ', 'debug': 'DEBUG'}.get(level, 'INFO ')
    print(f"{ts} {prefix} scraper: {msg}", file=_sys.stderr, flush=True)
    getattr(logger, level if level in ('error','warning','debug') else 'info', logger.info)(msg)


# ---------------------------------------------------------------------------
# ✅ Async scraper principal
# ---------------------------------------------------------------------------

async def _scrape_google_maps_async(
    niche: str,
    city: str,
    limit: int,
    only_without_website: bool = False,
    min_rating: float | None = None,
    min_reviews: int | None = None,
    only_with_instagram: bool = False,
    only_with_facebook: bool = False,
    # v12: novos parâmetros
    grid_bbox: str | None = None,
    grid_cell_km: float = 1.0,
    fast_mode: bool = False,
) -> list[dict]:
    """
    Versão assíncrona: abre o Google Maps, coleta as URLs e extrai
    até `limit` estabelecimentos com _PARALLEL_TABS abas simultâneas.

    v12 — novos modos:
      grid_bbox: "minLat,minLon,maxLat,maxLon" — divide a área em células
                 e busca em cada uma para garantir cobertura total.
      fast_mode: coleta rápida sem visitar cada ficha individualmente.
                 Retorna até 21 resultados por query com dados básicos.
    """
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    except ImportError:
        logger.error("[Maps] Playwright não instalado.")
        return []

    import pathlib

    # ── v12: Grid mode — divide bbox em células e agrega resultados ───────────
    if grid_bbox:
        bbox = _parse_bbox(grid_bbox)
        if bbox:
            min_lat, min_lon, max_lat, max_lon = bbox
            grid_points = _bbox_to_grid(min_lat, min_lon, max_lat, max_lon, grid_cell_km)
            all_grid_results: list[dict] = []
            seen_by_cid: set[str] = set()
            seen_by_name_addr: set[str] = set()

            logger.info(f"[Maps][Grid] Iniciando grid scraping com {len(grid_points)} células")
            for i, (lat, lon) in enumerate(grid_points):
                if len(all_grid_results) >= limit:
                    break
                geo_query = f"{niche} em {city}"
                geo_url = (
                    f"https://www.google.com/maps/search/{urllib.parse.quote(geo_query)}"
                    f"/@{lat},{lon},{15 + (1 if grid_cell_km < 0.5 else 0)}z"
                )
                logger.info(f"[Maps][Grid] Célula {i+1}/{len(grid_points)}: ({lat},{lon})")
                cell_results = await _scrape_google_maps_async(
                    niche=niche, city=city,
                    limit=min(limit - len(all_grid_results), 30),
                    only_without_website=only_without_website,
                    min_rating=min_rating, min_reviews=min_reviews,
                    only_with_instagram=only_with_instagram,
                    only_with_facebook=only_with_facebook,
                    fast_mode=fast_mode,
                    # SEM grid_bbox — recursão apenas 1 nível
                )
                for item in cell_results:
                    # Deduplicação por CID (mais confiável) ou nome+endereço
                    cid = item.get('_cid') or ''
                    dedup_key = f"{item.get('name','').lower()}|{(item.get('address') or '')[:30].lower()}"
                    if cid and cid in seen_by_cid:
                        continue
                    if dedup_key in seen_by_name_addr:
                        continue
                    if cid:
                        seen_by_cid.add(cid)
                    seen_by_name_addr.add(dedup_key)
                    all_grid_results.append(item)

                # Pausa entre células para evitar rate limiting
                await asyncio.sleep(random.uniform(1.5, 3.0))

            logger.info(f"[Maps][Grid] ✓ Total após deduplicação: {len(all_grid_results)} leads")
            return all_grid_results[:limit]

    # ── Sessão persistente ────────────────────────────────────────────────────
    # Salva cookies/localStorage entre execuções para evitar limitação do Google
    _STATE_PATH = pathlib.Path(__file__).resolve().parent / '.pw_session_state.json'

    results: list[dict] = []
    query = f"{niche} em {city}"
    maps_search_url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}"
    sem = asyncio.Semaphore(_PARALLEL_TABS)

    logger.info(f"[Maps] ── Iniciando sessão Playwright ────────────────────────────")
    logger.info(f"[Maps] Query    : {query!r}")
    logger.info(f"[Maps] URL Maps : {maps_search_url}")

    # ── Verifica dependências do sistema ─────────────────────────────────────
    dep_warnings = _check_system_deps()
    for w in dep_warnings:
        logger.warning(f"[Maps:dep] {w}")

    async with async_playwright() as p:
        browser = await _launch_browser_async(p)

        # Carrega sessão salva se existir (mantém cookies do Google entre execuções)
        context_kwargs = {}
        if _STATE_PATH.exists():
            try:
                context_kwargs['storage_state'] = str(_STATE_PATH)
                _pw_diag(f"[Maps][SESSION] ✓ Sessão anterior carregada: {_STATE_PATH}")
            except Exception:
                pass

        context = await _new_context_async(browser, **context_kwargs)

        # ── Injeta cookies reais do Google ────────────────────────────────────
        _inject_cookies = None
        try:
            from leads.cookie_manager import inject_google_cookies as _inject_cookies
        except ImportError:
            try:
                from cookie_manager import inject_google_cookies as _inject_cookies
            except ImportError:
                pass

        if _inject_cookies:
            cookies_ok = await _inject_cookies(context)
            if cookies_ok:
                _pw_diag("[Maps][COOKIES] ✓ Cookies do Google injetados com sucesso")
            else:
                _pw_diag("[Maps][COOKIES] ⚠️  Cookies não injetados — crie leads/google_cookies.json", "warning")
        else:
            _pw_diag("[Maps][COOKIES] ⚠️  cookie_manager não encontrado", "warning")

        search_page = await context.new_page()

        # Bloqueia assets pesados para acelerar
        await search_page.route(
            '**/*.{woff,woff2,ttf,otf,png,jpg,jpeg,gif,svg}',
            lambda r: r.abort()
        )

        _pw_diag("[Maps][PW-1] ══ Navegando para Google Maps ══")
        try:
            await search_page.goto(maps_search_url, wait_until='domcontentloaded', timeout=30000)
            _pw_diag("[Maps][PW-1] ✓ goto() concluído OK")
        except Exception as nav_err:
            _pw_diag(f"[Maps][PW-1] ✗ Falha na navegação: {nav_err}", 'error')
            await _log_page_state(search_page, 'nav_error')
            await _save_debug_screenshot(search_page, 'nav_error')
            await browser.close()
            return []

        await asyncio.sleep(2)

        # Log completo do estado logo após navegação
        current_url_after_nav = search_page.url
        page_title_after_nav = await search_page.title()
        _pw_diag(f"[Maps][PW-2] ══ Estado pós-goto ══")
        _pw_diag(f"[Maps][PW-2] URL   : {current_url_after_nav}")
        _pw_diag(f"[Maps][PW-2] Título: {page_title_after_nav}")

        # Detecta bloqueio imediato
        _title_l = page_title_after_nav.lower()
        _url_l = current_url_after_nav.lower()
        if any(w in _title_l for w in ('captcha', 'unusual traffic', 'robot', 'verify', 'sorry')):
            _pw_diag(f"[Maps][PW-2] ✗ BLOQUEIO/CAPTCHA no título: {page_title_after_nav!r}", 'error')
            await _save_debug_screenshot(search_page, 'blocked')
        if 'sorry' in _url_l or 'ipv4' in _url_l:
            _pw_diag(f"[Maps][PW-2] ✗ URL suspeita de bloqueio: {current_url_after_nav}", 'error')
            await _save_debug_screenshot(search_page, 'blocked_url')

        # Conta elementos presentes (diagnóstico básico)
        try:
            el_count = await search_page.evaluate("document.querySelectorAll('*').length")
            link_count = await search_page.evaluate("document.querySelectorAll('a[href]').length")
            _pw_diag(f"[Maps][PW-2] Elementos: {el_count} total | {link_count} links <a>")
        except Exception:
            pass

        # ── Consentimento robusto ─────────────────────────────────────────────
        _pw_diag("[Maps][PW-3] ══ Tentando aceitar consentimento ══")
        consent_accepted = await _handle_consent(search_page)
        if not consent_accepted:
            _pw_diag("[Maps][PW-3] Sem botão de consentimento (pode já estar aceito)")
        else:
            _pw_diag("[Maps][PW-3] ✓ Consentimento aceito com sucesso")

        # Log após consentimento
        url_after_consent = search_page.url
        title_after_consent = await search_page.title()
        _pw_diag(f"[Maps][PW-3] ══ Estado pós-consent ══")
        _pw_diag(f"[Maps][PW-3] URL   : {url_after_consent}")
        _pw_diag(f"[Maps][PW-3] Título: {title_after_consent}")
        try:
            el_count2 = await search_page.evaluate("document.querySelectorAll('*').length")
            link_count2 = await search_page.evaluate("document.querySelectorAll('a[href]').length")
            _pw_diag(f"[Maps][PW-3] Elementos pós-consent: {el_count2} total | {link_count2} links")
        except Exception:
            pass

        # ── Aguarda feed de resultados ────────────────────────────────────────
        feed_found = False
        feed_selector_used = None

        feed_selectors = [
            '[role="feed"] a',
            'div[aria-label*="Resultado"] a',
            'div[aria-label*="Result"] a',
            'div[aria-label*="resultado"] a',
            'a[href*="/maps/place/"]',           # fallback direto
        ]

        for sel in feed_selectors:
            try:
                await search_page.wait_for_selector(sel, timeout=10000)
                feed_found = True
                feed_selector_used = sel
                _pw_diag(f"[Maps][PW-4] ✓ Feed detectado via seletor: {sel!r}")
                break
            except Exception:
                _pw_diag(f"[Maps][PW-4] Seletor não encontrado: {sel!r}")
                continue

        if not feed_found:
            _pw_diag("[Maps][PW-4] ✗ FEED NÃO ENCONTRADO com nenhum seletor!", 'error')
            await _log_page_state(search_page, 'feed_not_found', html_chars=6000)
            await _save_debug_screenshot(search_page, 'feed_not_found')
            await browser.close()
            return []

        # ── Scroll progressivo ────────────────────────────────────────────────
        feed_handle = await search_page.query_selector('[role="feed"]')

        async def _scroll_feed(rounds: int):
            nonlocal feed_handle
            if feed_handle:
                try:
                    box = await feed_handle.bounding_box()
                    if box:
                        cx = box['x'] + box['width'] / 2
                        cy = box['y'] + box['height'] / 2
                        await search_page.mouse.move(cx, cy)
                        for _ in range(rounds):
                            await search_page.mouse.wheel(0, 900)
                            await asyncio.sleep(0.5)
                        await asyncio.sleep(1.2)
                        return
                except Exception:
                    pass
            for _ in range(rounds):
                await search_page.keyboard.press('PageDown')
                await asyncio.sleep(0.5)
            await asyncio.sleep(1.0)

        _pw_diag("[Maps][PW-4] Fazendo scroll para carregar resultados...")
        await _scroll_feed(10)

        # ── Coleta de URLs ────────────────────────────────────────────────────
        async def _collect_place_urls(seen: set) -> list[str]:
            urls = []

            # Seletor 1 — href direto com /maps/place/
            links = await search_page.query_selector_all('a[href*="/maps/place/"]')
            _pw_diag(f"[Maps][PW-5] Seletor 1 (a[href*/maps/place/]): {len(links)} elementos")
            for link in links:
                href = await link.get_attribute('href') or ''
                base = href.split('?')[0]
                if base not in seen and '/maps/place/' in base:
                    seen.add(base)
                    urls.append(href)

            # Seletor 2 — data-href
            if not urls:
                links2 = await search_page.query_selector_all('[data-href*="/maps/place/"]')
                _pw_diag(f"[Maps][PW-5] Seletor 2 (data-href): {len(links2)} elementos")
                for link in links2:
                    href = await link.get_attribute('data-href') or ''
                    base = href.split('?')[0]
                    if base not in seen and '/maps/place/' in base:
                        seen.add(base)
                        urls.append(href)

            # Seletor 3 — todos os <a>
            if not urls:
                all_links = await search_page.query_selector_all('a[href]')
                _pw_diag(f"[Maps][PW-5] Seletor 3 (todos os <a>): {len(all_links)} elementos")
                for link in all_links:
                    href = await link.get_attribute('href') or ''
                    if '/maps/place/' in href:
                        base = href.split('?')[0]
                        if base not in seen:
                            seen.add(base)
                            urls.append(href)

            # Seletor 4 — regex no HTML fonte
            if not urls:
                _pw_diag("[Maps][PW-5] Seletor 4: regex no HTML fonte...")
                page_source = await search_page.content()
                raw_urls = re.findall(
                    r'https://www\.google\.com/maps/place/[^\s"\'\\>]+', page_source
                )
                for raw in raw_urls:
                    raw = raw.rstrip('\\').split('"')[0].split("'")[0]
                    base = raw.split('?')[0]
                    if base not in seen and '/maps/place/' in base:
                        seen.add(base)
                        urls.append(raw)
                _pw_diag(f"[Maps][PW-5] Seletor 4 extraiu {len(urls)} URLs")

            return urls

        seen_urls: set[str] = set()
        place_urls = await _collect_place_urls(seen_urls)
        _pw_diag(f"[Maps][PW-5] ✓ 1ª coleta: {len(place_urls)} URLs de lugares")

        # Scroll extra se necessário
        if len(place_urls) < limit:
            _pw_diag("[Maps][PW-5] URLs insuficientes — scroll extra...")
            await _scroll_feed(12)
            extra = await _collect_place_urls(seen_urls)
            place_urls.extend(extra)
            _pw_diag(f"[Maps][PW-5] Após scroll extra: {len(place_urls)} URLs total")

        # ── Diagnóstico quando zero URLs ──────────────────────────────────────
        if not place_urls:
            _pw_diag("[Maps][PW-5] ✗ ZERO URLs de lugares encontradas!", 'error')
            _pw_diag(f"[Maps][PW-5] Feed selector usado: {feed_selector_used!r}", 'error')
            await _log_page_state(search_page, 'zero_urls', html_chars=6000)
            await _save_debug_screenshot(search_page, 'zero_urls')

            # Tenta uma última vez com scroll agressivo
            _pw_diag("[Maps][PW-5] Tentativa final: scroll agressivo...")
            await _scroll_feed(20)
            await asyncio.sleep(3)
            place_urls = await _collect_place_urls(seen_urls)
            _pw_diag(f"[Maps][PW-5] Tentativa final: {len(place_urls)} URLs")

            if not place_urls:
                _pw_diag("[Maps][PW-5] ✗ DIAGNÓSTICO FINAL: zero URLs. Causas:", 'error')
                logger.error("[Maps]   1. Google bloqueou o acesso (CAPTCHA / rate limit)")
                logger.error("[Maps]   2. Tela de consentimento não foi fechada")
                logger.error("[Maps]   3. Seletor do feed mudou (atualização do Maps)")
                logger.error("[Maps]   4. IP do servidor fora do Brasil (idioma diferente)")
                logger.error("[Maps]   5. Playwright desatualizado — rode: playwright install firefox")
                logger.error(f"[Maps]   6. Verifique pasta tmp/ do projeto")
                await search_page.close()
                await browser.close()
                return []

        place_urls = place_urls[:limit * 3]
        await search_page.close()
        _pw_diag(f"[Maps][PW-6] ══ {len(place_urls)} URLs — extraindo com {_PARALLEL_TABS} abas paralelas")

        # ── v12: FAST MODE — extração básica sem visitar cada ficha ──────────
        if fast_mode:
            _pw_diag("[Maps][FastMode] ✓ Fast mode ativo — extração básica da lista de resultados")
            fast_results = []
            for fu in place_urls[:limit]:
                # Extrai dados básicos da URL da lista (sem abrir a ficha)
                lat, lng = _extract_lat_lng_from_url(fu)
                cid = _extract_cid_from_url(fu)
                # Nome: extraído do segmento /maps/place/NOME/
                name_m = re.search(r'/maps/place/([^/]+)/', fu)
                raw_name = urllib.parse.unquote_plus(name_m.group(1)) if name_m else ''
                raw_name = raw_name.replace('+', ' ').strip()
                fast_results.append({
                    'name':             raw_name,
                    'category':         niche,
                    'city':             city,
                    'phone_number':     None,
                    'normalized_phone': None,
                    'website':          None,
                    'instagram':        None,
                    'address':          None,
                    'rating':           None,
                    'review_count':     0,
                    'maps_url':         _clean_maps_url(fu),
                    'source':           'google_maps_fast',
                    'status':           'novo',
                    '_latitude':        lat,
                    '_longitude':       lng,
                    '_cid':             cid,
                    '_coordinates':     {'lat': lat, 'lng': lng} if lat else None,
                })
                if len(fast_results) >= limit:
                    break
            _pw_diag(f"[Maps][FastMode] ✓ {len(fast_results)} leads em fast mode")
            await context.close()
            await browser.close()
            return fast_results

        # ── Extração paralela ─────────────────────────────────────────────────
        extract_kwargs = dict(
            city=city,
            only_without_website=only_without_website,
            min_rating=min_rating,
            min_reviews=min_reviews,
            only_with_instagram=only_with_instagram,
            only_with_facebook=only_with_facebook,
        )

        # v12: Lock + set para deduplicação em tempo real entre tabs paralelas
        _dedup_lock = asyncio.Lock()
        _seen_cids: set[str] = set()
        _seen_names: set[str] = set()

        async def _fetch_one(url: str) -> dict | None:
            async with sem:
                item = await _extract_place_async(context, url, **extract_kwargs)
                if item is None:
                    return None
                # Deduplicação em tempo real
                async with _dedup_lock:
                    cid = item.get('_cid') or ''
                    name_key = item.get('name', '').lower().strip()
                    if cid and cid in _seen_cids:
                        logger.debug(f"[Maps][Dedup] Duplicado por CID: {item['name']}")
                        return None
                    if name_key and name_key in _seen_names:
                        logger.debug(f"[Maps][Dedup] Duplicado por nome: {item['name']}")
                        return None
                    if cid:
                        _seen_cids.add(cid)
                    if name_key:
                        _seen_names.add(name_key)
                return item

        tasks = [asyncio.create_task(_fetch_one(u)) for u in place_urls]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        for item in all_results:
            if len(results) >= limit:
                break
            if isinstance(item, Exception):
                logger.warning(f"[Maps] Tarefa falhou: {item}")
            elif item is not None:
                results.append(item)
                logger.info(
                    f"[Maps] Extraído ({len(results)}/{limit}): {item['name']} | "
                    f"tel={item.get('phone_number', '—')} | "
                    f"ig={item.get('instagram', '—')} | "
                    f"rating={item.get('rating', '—')}"
                )

        # Salva sessão (cookies) ANTES de fechar o contexto
        try:
            await context.storage_state(path=str(_STATE_PATH))
            _pw_diag(f"[Maps][SESSION] ✓ Sessão salva em {_STATE_PATH}")
        except Exception:
            pass

        await context.close()
        await browser.close()

    _pw_diag(f"[Maps][PW-7] ══ Sessão encerrada. Total extraído: {len(results[:limit])} ══")
    return results[:limit]


# ---------------------------------------------------------------------------
# ✅ v6: scrape_google_maps — wrapper síncrono via subprocesso
# ---------------------------------------------------------------------------

def _find_playwright_browsers_path_for_subprocess():
    """Encontra o diretório de browsers do Playwright para injetar no subprocess."""
    import pathlib
    home = pathlib.Path.home()
    username = os.environ.get('USERNAME') or os.environ.get('USER') or ''
    candidates = [
        home / 'AppData' / 'Local' / 'ms-playwright',   # Windows
        home / '.cache' / 'ms-playwright',               # Linux/Mac
        pathlib.Path('/root/.cache/ms-playwright'),
    ]
    if username:
        candidates.append(pathlib.Path(f'/home/{username}/.cache/ms-playwright'))
    for c in candidates:
        if c.exists() and list(c.glob('firefox-*')):
            return str(c)
    return None


def scrape_google_maps(
    niche: str,
    city: str,
    limit: int,
    only_without_website: bool = False,
    min_rating: float | None = None,
    min_reviews: int | None = None,
    only_with_instagram: bool = False,
    only_with_facebook: bool = False,
    # v12: novos parâmetros
    grid_bbox: str | None = None,
    grid_cell_km: float = 1.0,
    fast_mode: bool = False,
) -> list[dict]:
    """
    Wrapper síncrono v7 — chama scraper_runner.py como subprocesso isolado.

    v12 — novos parâmetros:
      grid_bbox (str): "minLat,minLon,maxLat,maxLon" — varredura em grade.
                       Ex: "-21.25,-47.85,-21.15,-47.75" para Ribeirão Preto centro.
      grid_cell_km (float): tamanho de cada célula da grade em km (padrão 1.0).
      fast_mode (bool): coleta rápida sem abrir cada ficha. Menos dados, mais velocidade.

    ROLLBACK STAGES (procure nos logs do Django):
      [STEP 1] Verificação do ambiente e runner
      [STEP 2] Serialização dos args e montagem do subprocesso
      [STEP 3] Subprocesso iniciado
      [STEP 4] Subprocesso concluído — parsing do resultado
      [STEP 5] JSON parsed — retornando leads
    """
    import json
    import base64
    import subprocess
    from pathlib import Path

    # ── STEP 1: Verificação do ambiente ──────────────────────────────────────
    logger.info("[Maps][STEP 1] ══ Verificando ambiente do scraper ══")
    logger.info(f"[Maps][STEP 1] Python executable : {sys.executable}")
    logger.info(f"[Maps][STEP 1] PID corrente      : {os.getpid()}")
    logger.info(f"[Maps][STEP 1] DJANGO_SETTINGS   : {os.environ.get('DJANGO_SETTINGS_MODULE', '<não definido>')}")
    logger.info(f"[Maps][STEP 1] Parâmetros        : niche={niche!r} city={city!r} limit={limit}")
    logger.info(f"[Maps][STEP 1] Filtros           : sem_site={only_without_website} min_rating={min_rating} min_reviews={min_reviews} ig={only_with_instagram} fb={only_with_facebook}")

    runner_path = Path(__file__).parent / 'scraper_runner.py'
    leads_dir    = str(Path(__file__).resolve().parent)
    project_root = str(Path(__file__).resolve().parent.parent)
    settings_module = os.environ.get('DJANGO_SETTINGS_MODULE', 'core.settings')

    logger.info(f"[Maps][STEP 1] leads_dir    : {leads_dir}")
    logger.info(f"[Maps][STEP 1] project_root : {project_root}")
    logger.info(f"[Maps][STEP 1] runner_path  : {runner_path}")

    if not runner_path.exists():
        logger.error(f"[Maps][STEP 1] ✗ FALHOU — scraper_runner.py não encontrado em {runner_path}")
        logger.error("[Maps][STEP 1]   → Certifique-se que scraper_runner.py está na pasta leads/")
        return []
    logger.info(f"[Maps][STEP 1] ✓ scraper_runner.py encontrado")

    # ── STEP 2: Montagem do subprocesso ──────────────────────────────────────
    logger.info("[Maps][STEP 2] ══ Preparando subprocesso ══")

    args = {
        '_settings_module': settings_module,
        'niche': niche,
        'city': city,
        'limit': limit,
        'only_without_website': only_without_website,
        'min_rating': min_rating,
        'min_reviews': min_reviews,
        'only_with_instagram': only_with_instagram,
        'only_with_facebook': only_with_facebook,
        # v12
        'grid_bbox': grid_bbox,
        'grid_cell_km': grid_cell_km,
        'fast_mode': fast_mode,
    }
    try:
        args_b64 = base64.b64encode(json.dumps(args).encode('utf-8')).decode('ascii')
        logger.info(f"[Maps][STEP 2] ✓ Args serializados (base64 len={len(args_b64)})")
    except Exception as e:
        logger.error(f"[Maps][STEP 2] ✗ FALHOU ao serializar args: {e}")
        return []

    # Monta env do subprocesso
    subprocess_env = os.environ.copy()
    subprocess_env['PYTHONIOENCODING'] = 'utf-8'
    subprocess_env['PYTHONUNBUFFERED'] = '1'
    subprocess_env['DJANGO_SETTINGS_MODULE'] = settings_module

    # Injeta PLAYWRIGHT_BROWSERS_PATH se não estiver definido
    if not subprocess_env.get('PLAYWRIGHT_BROWSERS_PATH'):
        pw_path = _find_playwright_browsers_path_for_subprocess()
        if pw_path:
            subprocess_env['PLAYWRIGHT_BROWSERS_PATH'] = pw_path
            logger.info(f"[Maps][STEP 2] ✓ PLAYWRIGHT_BROWSERS_PATH → {pw_path}")
        else:
            logger.warning(
                "[Maps][STEP 2] ⚠️  PLAYWRIGHT_BROWSERS_PATH não encontrado. "
                "Execute: playwright install firefox"
            )
    else:
        logger.info(f"[Maps][STEP 2] ✓ PLAYWRIGHT_BROWSERS_PATH já definido: {subprocess_env['PLAYWRIGHT_BROWSERS_PATH']}")

    timeout_seconds = int(os.environ.get('MAPS_SCRAPER_TIMEOUT', 360))
    cmd = [sys.executable, str(runner_path), args_b64]
    logger.info(f"[Maps][STEP 2] ✓ Timeout     : {timeout_seconds}s")
    logger.info(f"[Maps][STEP 2] ✓ Comando     : {' '.join(cmd[:2])} <base64_args>")
    logger.info(f"[Maps][STEP 2] ✓ cwd         : {leads_dir}")

    # ── STEP 3: Executa subprocesso ──────────────────────────────────────────
    logger.info("[Maps][STEP 3] ══ Iniciando subprocesso ══")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout_seconds,
            cwd=leads_dir,
            env=subprocess_env,
        )
        logger.info(f"[Maps][STEP 3] ✓ Subprocesso concluído — exit code: {proc.returncode}")
    except subprocess.TimeoutExpired:
        logger.error(
            f"[Maps][STEP 3] ✗ TIMEOUT ({timeout_seconds}s) expirado. "
            "Aumente MAPS_SCRAPER_TIMEOUT no .env ou reduza o limite de leads."
        )
        return []
    except FileNotFoundError:
        logger.error(f"[Maps][STEP 3] ✗ Python não encontrado: {sys.executable}")
        return []
    except Exception:
        import traceback as _tb
        logger.error(f"[Maps][STEP 3] ✗ Erro inesperado ao lançar subprocesso:\n{_tb.format_exc()}")
        return []

    # ── STEP 4: Parsing do resultado ─────────────────────────────────────────
    logger.info("[Maps][STEP 4] ══ Processando saída do subprocesso ══")

    # Sempre loga o stderr completo do filho (aqui ficam os logs do runner)
    if proc.stderr.strip():
        logger.info("[Maps][STEP 4] ── stderr do subprocesso (logs internos) ──────")
        for line in proc.stderr.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if any(w in stripped for w in ('ERROR', 'CRITICAL', 'ERRO', 'FATAL', '✗')):
                logger.error(f"[Maps:worker] {stripped}")
            elif any(w in stripped for w in ('WARNING', 'WARN', 'AVISO', '⚠')):
                logger.warning(f"[Maps:worker] {stripped}")
            else:
                logger.info(f"[Maps:worker] {stripped}")
        logger.info("[Maps][STEP 4] ── fim do stderr ────────────────────────────────")
    else:
        logger.warning("[Maps][STEP 4] ⚠️  stderr do subprocesso está VAZIO — possível crash silencioso!")
        logger.warning("[Maps][STEP 4]   → Verifique se PYTHONUNBUFFERED=1 está no .env do Django")

    if proc.returncode != 0:
        logger.error(f"[Maps][STEP 4] ✗ Subprocesso falhou com exit code {proc.returncode}")
        stdout_preview = proc.stdout[:3000] if proc.stdout else "<vazio>"
        logger.error(f"[Maps][STEP 4]   stdout do filho:\n{stdout_preview}")
        return []

    # Busca linha de resultado
    result_line = None
    for line in proc.stdout.splitlines():
        if line.startswith('__SCRAPER_RESULT__'):
            result_line = line[len('__SCRAPER_RESULT__'):]
            break

    if result_line is None:
        logger.error("[Maps][STEP 4] ✗ Marcador __SCRAPER_RESULT__ não encontrado no stdout!")
        logger.error("[Maps][STEP 4]   Causas comuns:")
        logger.error("[Maps][STEP 4]   → O runner crashou antes de imprimir o resultado")
        logger.error("[Maps][STEP 4]   → Erro de importação no runner (veja stderr acima)")
        logger.error("[Maps][STEP 4]   → stdout do filho (primeiros 2000 chars):")
        logger.error(f"[Maps][STEP 4]   {proc.stdout[:2000]!r}")
        return []

    logger.info(f"[Maps][STEP 4] ✓ Marcador __SCRAPER_RESULT__ encontrado (payload len={len(result_line)})")

    # ── STEP 5: Parse do JSON ─────────────────────────────────────────────────
    logger.info("[Maps][STEP 5] ══ Deserializando JSON de leads ══")
    try:
        results = json.loads(result_line)
        if not isinstance(results, list):
            logger.error(f"[Maps][STEP 5] ✗ JSON retornou tipo inesperado: {type(results)} — esperado list")
            return []
        logger.info(f"[Maps][STEP 5] ✓ {len(results)} leads recebidos do subprocesso")
        if len(results) == 0:
            logger.warning("[Maps][STEP 5] ⚠️  Lista de leads está VAZIA")
            logger.warning("[Maps][STEP 5]   → Verifique os logs [Maps:worker] acima para saber onde falhou")
            logger.warning("[Maps][STEP 5]   → Causas comuns: CAPTCHA, consentimento, seletor mudou, IP fora do BR")
            logger.warning("[Maps][STEP 5]   → Verifique screenshots em pasta tmp/ do projeto")
        else:
            for i, lead in enumerate(results[:3]):
                logger.info(f"[Maps][STEP 5]   Lead {i+1}: {lead.get('name')} | tel={lead.get('phone_number')} | city={lead.get('city')}")
        return results
    except json.JSONDecodeError as e:
        logger.error(f"[Maps][STEP 5] ✗ Erro ao parsear JSON: {e}")
        logger.error(f"[Maps][STEP 5]   Payload (500 chars): {result_line[:500]!r}")
        return []


# ---------------------------------------------------------------------------
# Extração de dados de um único lugar
# ---------------------------------------------------------------------------

_JS_EXTRACT_ALL = r"""
() => {
    const R = {
        name: null, category: null, phone: null, address: null,
        website: null, rating: null, review_count: null,
        instagram: null, facebook: null, youtube: null, twitter: null,
        linkedin: null, tiktok: null, whatsapp_link: null,
        bio: null, hours: {}, share_url: null, og_image: null,
        maps_url: null, price_range: null, plus_code: null,
        amenities: [], popular_times: null, total_photos: null,
        // v12: novos campos
        latitude: null, longitude: null, cid: null, kgmid: null,
        order_online: null, menu: null, reservations: null,
        coordinates: null,
    };

    // ── v12: KGMID — Knowledge Graph Machine ID ───────────────────────────────
    // É o identificador mais estável do Google (/g/11abc123)
    // Extraído de: URL canônica, link[rel=canonical], APP_INITIALIZATION_STATE
    try {
        const canonical = document.querySelector('link[rel="canonical"]');
        if (canonical) {
            const m = canonical.href.match(/\/maps\/place\/[^/]+\/(\/g\/[A-Za-z0-9_]+)/);
            if (m) R.kgmid = m[1];
        }
    } catch(e) {}
    if (!R.kgmid) {
        // Busca na URL atual
        const urlM = window.location.href.match(/\/(\/g\/[A-Za-z0-9_]+)/);
        if (urlM) R.kgmid = urlM[1];
    }
    if (!R.kgmid) {
        // Busca em data-pid (place id) ou data-cid em elementos do DOM
        for (const el of document.querySelectorAll('[data-pid]')) {
            const pid = el.getAttribute('data-pid') || '';
            if (pid.startsWith('/g/')) { R.kgmid = pid; break; }
        }
    }

    // ── v12: CID — Customer ID numérico do Google ────────────────────────────
    // Identificador numérico permanente de ~19 dígitos
    try {
        // Método 1: data-cid no DOM
        for (const el of document.querySelectorAll('[data-cid]')) {
            const cid = el.getAttribute('data-cid') || '';
            if (/^\d{10,20}$/.test(cid)) { R.cid = cid; break; }
        }
        // Método 2: URL atual (formato ?cid=NUMERO)
        if (!R.cid) {
            const cidM = window.location.href.match(/[?&;]cid=(\d+)/);
            if (cidM) R.cid = cidM[1];
        }
        // Método 3: Hex pairs no URL → CID decimal
        // URL Maps: /maps/place/NAME/0xHEX:0xHEX → segundo hex é o CID
        if (!R.cid) {
            const hexM = window.location.href.match(/\/maps\/place\/[^/]+\/0x[0-9a-f]+:0x([0-9a-f]+)/i);
            if (hexM) {
                try {
                    R.cid = BigInt('0x' + hexM[1]).toString();
                } catch(e) {}
            }
        }
    } catch(e) {}

    // ── v12: Latitude e Longitude — da URL canônica ──────────────────────────
    // O Google Maps sempre inclui @lat,lng,zoom na URL do lugar
    try {
        const latLngM = window.location.href.match(/@(-?\d+\.\d+),(-?\d+\.\d+),\d+/);
        if (latLngM) {
            R.latitude = parseFloat(latLngM[1]);
            R.longitude = parseFloat(latLngM[2]);
        }
        // Fallback: formato !3dlat!4dlng
        if (!R.latitude) {
            const m2 = window.location.href.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/);
            if (m2) {
                R.latitude = parseFloat(m2[1]);
                R.longitude = parseFloat(m2[2]);
            }
        }
        if (R.latitude && R.longitude) {
            R.coordinates = { lat: R.latitude, lng: R.longitude };
        }
    } catch(e) {}

    // ── v12: Order online / Menu / Reservations ───────────────────────────────
    // Botões de ação na ficha do Maps
    try {
        // Pedido online: iFood, Rappi, "Fazer pedido", etc.
        const orderSelectors = [
            'a[href*="ifood"]', 'a[href*="rappi"]', 'a[href*="ubereats"]',
            'a[href*="deliveroo"]', 'a[href*="aiqfome"]',
            'a[aria-label*="Pedir"]', 'a[aria-label*="pedido"]',
            'a[aria-label*="Fazer pedido"]', 'a[data-item-id*="order"]',
            'button[aria-label*="Pedir"]', 'button[aria-label*="pedido"]',
        ];
        for (const sel of orderSelectors) {
            const el = document.querySelector(sel);
            if (el) { R.order_online = el.href || el.getAttribute('data-href') || 'disponível'; break; }
        }

        // Cardápio/Menu
        const menuSelectors = [
            'a[data-item-id*="menu"]', 'a[aria-label*="cardápio"]',
            'a[aria-label*="menu"]', 'a[aria-label*="Menu"]',
            'a[href*="menu"]',
        ];
        for (const sel of menuSelectors) {
            const el = document.querySelector(sel);
            if (el) { R.menu = el.href || el.getAttribute('data-href') || 'disponível'; break; }
        }

        // Reservas
        const resSelectors = [
            'a[data-item-id*="reserv"]', 'a[aria-label*="Reservar"]',
            'a[aria-label*="reserv"]', 'a[href*="reserve"]',
            'a[href*="opentable"]', 'a[href*="resy.com"]',
        ];
        for (const sel of resSelectors) {
            const el = document.querySelector(sel);
            if (el) { R.reservations = el.href || el.getAttribute('data-href') || 'disponível'; break; }
        }
    } catch(e) {}

    // ── v12: Popular Times ────────────────────────────────────────────────────
    // Extrai padrões de movimento por dia/hora quando disponíveis
    try {
        const popularTimesData = {};
        const dayMap = {
            'domingo': 'dom', 'segunda-feira': 'seg', 'segunda': 'seg',
            'terça-feira': 'ter', 'terca-feira': 'ter', 'terça': 'ter',
            'quarta-feira': 'qua', 'quarta': 'qua',
            'quinta-feira': 'qui', 'quinta': 'qui',
            'sexta-feira': 'sex', 'sexta': 'sex',
            'sábado': 'sab', 'sabado': 'sab',
        };
        // popular times ficam em divs com aria-label "X% ocupado às HH:MM"
        const ptEls = document.querySelectorAll('[aria-label*="ocupado"], [aria-label*="busy"], [aria-label*="lotado"]');
        for (const el of ptEls) {
            const lbl = el.getAttribute('aria-label') || '';
            // "42% ocupado às 18:00 na segunda-feira"
            const m = lbl.match(/(\d+)%.*?(\d{1,2}:\d{2}).*?(segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo)/i);
            if (m) {
                const pct = parseInt(m[1]);
                const hour = m[2];
                const dayKey = dayMap[m[3].toLowerCase()] || m[3].toLowerCase().slice(0,3);
                if (!popularTimesData[dayKey]) popularTimesData[dayKey] = {};
                popularTimesData[dayKey][hour] = pct;
            }
        }
        if (Object.keys(popularTimesData).length > 0) {
            R.popular_times = popularTimesData;
        }
    } catch(e) {}

    const bad = new Set(['explore','reel','reels','p','stories','tv','accounts',
                         'tags','share','sharer','intent','home','watch','results',
                         'search','jobs','feed','ads','about','legal','privacy',
                         'support','notifications','explore','highlights']);

    // ── Nome ──────────────────────────────────────────────────────────────────
    const h1 = document.querySelector('h1');
    if (h1) R.name = h1.textContent.trim();

    // ── og:image e foto principal da ficha ───────────────────────────────────
    const og = document.querySelector('meta[property="og:image"]');
    if (og && og.content) R.og_image = og.content;
    // Fallback: imagem hero do topo da ficha (button.aoRNLd > img)
    if (!R.og_image) {
        const heroImg = document.querySelector('button.aoRNLd img, .RZ66Rb img');
        if (heroImg && heroImg.src && !heroImg.src.includes('data:')) {
            R.og_image = heroImg.src;
        }
    }

    // ── Categoria ─────────────────────────────────────────────────────────────
    // O botão de categoria fica logo abaixo do h1 — múltiplos seletores por segurança
    const notCat = new Set(['Rotas','Salvar','Compartilhar','Avaliar','Ligar','Enviar',
                    'Sugerir','Adicionar','Ordenar','Pesquisar','Fotos','Avaliações',
                    'Sobre','Visão geral','Serviços','Produtos']);
    const catCandidates = [
        document.querySelector('button[jsaction*="category"]'),
        document.querySelector('[jsan*="category"]'),
        document.querySelector('div.fontBodyMedium button.DkEaL'),
        document.querySelector('.LBgpqf button'),
        document.querySelector('.skqShb button'),
        // Estrutura nova: span.fontBodyMedium logo após o h1
        (() => {
            const spans = document.querySelectorAll('span.fontBodyMedium');
            for (const s of spans) {
                const btn = s.querySelector('button') || s;
                const t = btn.textContent.trim();
                if (t && t.length > 2 && t.length < 80 && !notCat.has(t)) return btn;
            }
            return null;
        })(),
        // Fallback: primeiro button[jsaction] após h1 que não seja ação conhecida
        (() => {
            const h1el = document.querySelector('h1');
            if (!h1el) return null;
            let el = h1el.nextElementSibling;
            for (let i = 0; i < 5 && el; i++, el = el.nextElementSibling) {
                const btn = el.querySelector('button') || (el.tagName === 'BUTTON' ? el : null);
                if (btn) {
                    const t = btn.textContent.trim();
                    if (t && !notCat.has(t) && t.length < 80) return btn;
                }
            }
            return null;
        })(),
    ];
    for (const catEl of catCandidates) {
        if (!catEl) continue;
        const catText = catEl.textContent.trim();
        if (catText && !notCat.has(catText) && catText.length > 2 && catText.length < 80) {
            R.category = catText;
            break;
        }
    }

    // ── Rating e total de reviews — via seletores diretos (mais confiável) ─────
    // O Google Maps exibe o rating em span.ceNzKf e total em button com aria-label
    if (!R.rating) {
        const ratingEl =
            document.querySelector('span.ceNzKf') ||
            document.querySelector('span.kvMYJc') ||
            document.querySelector('div.F7nice span[aria-hidden="true"]');
        if (ratingEl) {
            const n = parseFloat((ratingEl.textContent || '').trim().replace(',', '.'));
            if (!isNaN(n) && n >= 1 && n <= 5) R.rating = n;
        }
    }
    if (!R.review_count) {
        // Botão "XXX avaliações" no topo da ficha
        const rcEl =
            document.querySelector('button[aria-label*="avaliações"] span') ||
            document.querySelector('span.RDApEe') ||
            document.querySelector('span[aria-label*="avaliações"]') ||
            document.querySelector('div.F7nice span span');
        if (rcEl) {
            const txt = (rcEl.getAttribute('aria-label') || rcEl.textContent || '').replace(/\D/g, '');
            if (txt) {
                const n = parseInt(txt, 10);
                if (!isNaN(n) && n > 0) R.review_count = n;
            }
        }
    }

    // ── Aria-labels: varre todos para extrair phone, address, hours, rating ───
    const labelEls = document.querySelectorAll('[aria-label]');
    for (const el of labelEls) {
        const lbl = el.getAttribute('aria-label') || '';
        const lblL = lbl.toLowerCase();

        // Telefone
        if (!R.phone && (lblL.includes('telefone') || lblL.includes('phone'))) {
            const m = lbl.match(/[\d\s()\-\+]{7,}/);
            if (m) R.phone = m[0].trim();
        }

        // Endereço
        if (!R.address && (lblL.includes('endereço') || lblL.includes('address'))) {
            let addr = lbl.replace(/endereço:?/i,'').replace(/address:?/i,'').trim();
            if (addr.length > 5) R.address = addr;
        }

        // Rating
        if (!R.rating) {
            const rm = lbl.match(/([1-5][.,]\d)\s*(?:estrelas?|stars?)/i);
            if (rm) R.rating = parseFloat(rm[1].replace(',','.'));
        }

        // Review count — trata "1.203" e "1,203" corretamente
        if (!R.review_count) {
            const rcm = lbl.match(/([\d][.\d,]*[\d]|[\d]+)\s*(?:avaliações|avaliação|reviews?|comentários)/i);
            if (rcm) {
                const digits = rcm[1].replace(/[^\d]/g,'');
                if (digits) {
                    const n = parseInt(digits, 10);
                    if (!isNaN(n) && n > 0) R.review_count = n;
                }
            }
        }

        // Horários — linha com múltiplos dias
        const dayMatches = [...lbl.matchAll(
            /(segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo)[\s\-feira]*\s*:?\s*([\d:–\-\s]+|fechado|aberto\s*24\s*horas|atendimento\s*24\s*horas)/gi
        )];
        if (dayMatches.length >= 2) {
            const dayMap = {
                'segunda':'seg','terça':'ter','terca':'ter',
                'quarta':'qua','quinta':'qui','sexta':'sex',
                'sábado':'sab','sabado':'sab','domingo':'dom'
            };
            for (const [, rawDay, rawHrs] of dayMatches) {
                const key = dayMap[rawDay.toLowerCase().trim()];
                if (!key || R.hours[key]) continue;
                const hm = rawHrs.match(/(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})/);
                if (hm) R.hours[key] = hm[1] + '–' + hm[2];
                else if (/fechado|closed/i.test(rawHrs)) R.hours[key] = 'Fechado';
                else if (/24\s*hora|atendimento\s*24/i.test(rawHrs)) R.hours[key] = '00:00–23:59';
            }
        }
        // Horários — formato "dia, HH:MM–HH:MM" ou "dia, Fechado" (aria-label individual)
        const singleDay = lbl.match(/^(segunda[\-\s]?feira|terça[\-\s]?feira|quarta[\-\s]?feira|quinta[\-\s]?feira|sexta[\-\s]?feira|sábado|sabado|domingo),?\s+(.+)/i);
        if (singleDay) {
            const dayMapFull = {
                'segunda-feira':'seg','segunda feira':'seg','terça-feira':'ter','terca-feira':'ter',
                'terça feira':'ter','terca feira':'ter','quarta-feira':'qua','quarta feira':'qua',
                'quinta-feira':'qui','quinta feira':'qui','sexta-feira':'sex','sexta feira':'sex',
                'sábado':'sab','sabado':'sab','domingo':'dom'
            };
            const dkey = dayMapFull[singleDay[1].toLowerCase().trim()];
            if (dkey && !R.hours[dkey]) {
                const rawHrs2 = singleDay[2];
                // Suporte a 2 períodos: "08:00–11:30 / 14:00–17:00"
                const allP2 = [...rawHrs2.matchAll(/(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})/g)];
                if (allP2.length >= 2) R.hours[dkey] = allP2.map(p => p[1]+'–'+p[2]).join(' / ');
                else if (allP2.length === 1) R.hours[dkey] = allP2[0][1] + '–' + allP2[0][2];
                else if (/fechado|closed/i.test(rawHrs2)) R.hours[dkey] = 'Fechado';
                else if (/24\s*hora|atendimento\s*24/i.test(rawHrs2)) R.hours[dkey] = '00:00–23:59';
            }
        }
    }

    // ── Bio / descrição ───────────────────────────────────────────────────────
    for (const sel of ['[aria-label*="Sobre"]','[aria-label*="Resumo"]',
                       '[data-item-id*="editorial"]',
                       'div.PYvSYb','div.ZD2Oce','span.HlvSq',
                       'div.iP2t7d > span', 'span.P5Bobd']) {
        const el = document.querySelector(sel);
        if (el) {
            const t = el.textContent.trim();
            // Relaxado: mínimo 5 chars (era 20) para não perder bios curtas
            if (t.length > 5 && t.length < 1000) { R.bio = t; break; }
        }
    }

    // ── Website e redes sociais — todos os <a href> + texto da página ────────
    // Primeiro: links diretos
    for (const a of document.querySelectorAll('a[href]')) {
        const href = (a.href || '').trim();
        if (!href || href.startsWith('javascript:')) continue;

        // Instagram
        if (!R.instagram) {
            const m = href.match(/instagram\.com\/([A-Za-z0-9._]{2,50})/);
            if (m && !bad.has(m[1].toLowerCase()))
                R.instagram = '@' + m[1].replace(/\/$/,'');
        }
        // Facebook
        if (!R.facebook) {
            const m = href.match(/facebook\.com\/([A-Za-z0-9._\-]{2,80})/);
            if (m && !bad.has(m[1].toLowerCase()))
                R.facebook = href.replace(/[?#].*/,'');
        }
        // YouTube
        if (!R.youtube) {
            const m = href.match(/youtube\.com\/(?:channel\/|c\/|@)([A-Za-z0-9._\-]{2,80})/);
            if (m && !bad.has(m[1].toLowerCase()))
                R.youtube = href.replace(/[?#].*/,'');
        }
        // Twitter/X
        if (!R.twitter) {
            const m = href.match(/(?:twitter|x)\.com\/([A-Za-z0-9._]{2,50})/);
            if (m && !bad.has(m[1].toLowerCase()))
                R.twitter = href.replace(/[?#].*/,'');
        }
        // LinkedIn
        if (!R.linkedin) {
            const m = href.match(/linkedin\.com\/(?:company|in)\/([A-Za-z0-9._\-]{2,80})/);
            if (m && !bad.has(m[1].toLowerCase()))
                R.linkedin = href.replace(/[?#].*/,'');
        }
        // WhatsApp
        if (!R.phone) {
            const m = href.match(/wa\.me\/(\d{10,15})/);
            if (m) R.phone = m[1];
        }
        // Website — qualquer link externo que não seja redes sociais ou Google
        if (!R.website) {
            if (href.startsWith('http') &&
                !href.includes('google') && !href.includes('goo.gl') &&
                !href.includes('instagram.com') && !href.includes('facebook.com') &&
                !href.includes('youtube.com') && !href.includes('twitter.com') &&
                !href.includes('x.com') && !href.includes('linkedin.com') &&
                !href.includes('wa.me') && !href.includes('whatsapp.com') &&
                !href.includes('tiktok.com')) {
                R.website = href;
            }
        }
    }

    // Segundo: texto visível (URLs escritas como texto) — captura handles no body
    // Isso é especialmente útil para iframes e seções "Resultados da Web"
    const bodyText = document.body ? document.body.innerText : '';
    if (!R.instagram) {
        // Handle @usuario mencionado próximo a "Instagram"
        const igM = bodyText.match(/instagram[^\n]{0,50}@([A-Za-z0-9._]{2,50})/i) ||
                    bodyText.match(/@([A-Za-z0-9._]{2,50})[^\n]{0,30}instagram/i) ||
                    bodyText.match(/instagram\.com\/([A-Za-z0-9._]{2,50})/i);
        if (igM) {
            const handle = igM[1].replace(/[^A-Za-z0-9._]/g, '');
            if (handle && !bad.has(handle.toLowerCase())) R.instagram = '@' + handle;
        }
    }

    // ── Telefone via botão "Ligar" (href tel:) ──────────────────────────────
    if (!R.phone) {
        const telLink = document.querySelector('a[href^="tel:"]');
        if (telLink) {
            R.phone = decodeURIComponent(telLink.getAttribute('href').replace('tel:','').trim());
        }
    }

    // ── WhatsApp direto (botão wa.me na ficha) ────────────────────────────────
    const waLink = document.querySelector('a[href*="wa.me/"], a[href*="api.whatsapp.com/send"]');
    if (waLink) {
        const waHref = waLink.getAttribute('href') || '';
        const waM = waHref.match(/(?:wa\.me\/|phone=)(\d{10,15})/);
        if (waM) R.whatsapp_link = waM[1];
    }

    // ── TikTok ────────────────────────────────────────────────────────────────
    if (!R.tiktok) {
        for (const a of document.querySelectorAll('a[href*="tiktok.com"]')) {
            const m = a.href.match(/tiktok\.com\/@([A-Za-z0-9._]{2,50})/);
            if (m && !bad.has(m[1].toLowerCase())) { R.tiktok = '@' + m[1]; break; }
        }
    }

    // ── Faixa de preço ($, $$, $$$, $$$$) ────────────────────────────────────
    for (const el of document.querySelectorAll('[aria-label]')) {
        const lbl = el.getAttribute('aria-label') || '';
        const pm = lbl.match(/Faixa\s+de\s+pre[cç]o[:\s]+(.{1,20})/i) ||
                   lbl.match(/Price\s+range[:\s]+(.{1,20})/i) ||
                   lbl.match(/^([$€£]{1,4})$/);
        if (pm) { R.price_range = pm[1].trim(); break; }
    }
    // Fallback: texto "$$$" solto no painel
    if (!R.price_range) {
        const priceEl = document.querySelector('span.mgr77e') ||
                        document.querySelector('span[aria-label*="preço"]');
        if (priceEl) R.price_range = priceEl.textContent.trim().slice(0, 10);
    }

    // ── Plus Code ─────────────────────────────────────────────────────────────
    // O Plus Code aparece em: aria-label, data-item-id, ou como texto puro no painel
    for (const el of document.querySelectorAll('[aria-label]')) {
        const lbl = el.getAttribute('aria-label') || '';
        // Formato no aria-label: "Plus Code: Q5QX+R5" ou "Q5QX+R5 Jardim Botânico"
        const pcm = lbl.match(/Plus\s+Code[:\s]+([A-Z0-9]{4,6}\+[A-Z0-9]{2,3})/i) ||
                    lbl.match(/\b([A-Z0-9]{4,6}\+[A-Z0-9]{2,3})\b/);
        if (pcm) { R.plus_code = decodeURIComponent(pcm[1]); break; }
    }
    if (!R.plus_code) {
        // data-item-id pode conter o plus code codificado
        for (const el of document.querySelectorAll('[data-item-id]')) {
            const did = el.getAttribute('data-item-id') || '';
            const pcm = did.match(/plus_code:([A-Z0-9%+]{6,})/i);
            if (pcm) { R.plus_code = decodeURIComponent(pcm[1]); break; }
        }
    }
    if (!R.plus_code) {
        // Texto puro no painel: "Q5QX+R5 Jardim Botânico, Ribeirão Preto"
        const allText = document.body ? document.body.innerText : '';
        // Plus code: 4-6 chars alfanum + '+' + 2-3 chars — formato OLC padrão
        const plm = allText.match(/\b([A-Z0-9]{4,6}\+[A-Z0-9]{2,3})\b/);
        if (plm) R.plus_code = plm[1];
    }

    // ── Amenidades / Atributos do lugar ──────────────────────────────────────
    // O Google Maps exibe atributos em várias estruturas dependendo da versão/categoria.
    // Coletamos de todas as fontes conhecidas e deduplicamos.
    const amenitySelectors = [
        // Containers de atributos v2024 (acessibilidade, pagamentos, etc.)
        'div.iP2t7d span',
        'div.E0DTEd span',
        'li.hpLkke span',
        'div.sSHqwe span',
        'div.lX8Tbe span',
        'div.ekb8yd span',
        // aria-label com atributos comuns
        '[aria-label*="Aceita"]',
        '[aria-label*="Wi-Fi"]',
        '[aria-label*="Acessív"]',
        '[aria-label*="Estacionamento"]',
        '[aria-label*="Pagamento"]',
        '[aria-label*="Refeição"]',
        '[aria-label*="Serviço"]',
        '[aria-label*="Planejamento"]',
        '[aria-label*="Crianças"]',
        '[aria-label*="Animal"]',
        '[aria-label*="LGBTQ"]',
        // Seção "Sobre o lugar" / informações adicionais
        '[data-item-id*="attribute"] span',
        '[data-item-id*="amenity"] span',
        // Estrutura com ícone + texto: div.Io6YTe
        'div.Io6YTe',
        // Lista de recursos (v2023)
        'ul.ZjVtHb li',
    ];
    const seenAmenities = new Set();
    for (const sel of amenitySelectors) {
        for (const el of document.querySelectorAll(sel)) {
            // Prioriza aria-label; cai para textContent
            const t = (el.getAttribute('aria-label') || el.textContent || '').trim()
                       .replace(/\s+/g, ' ');
            if (t && t.length > 3 && t.length < 120 && !seenAmenities.has(t)) {
                // Filtra textos que são claramente botões de ação ou navegação
                const skip = /^(Rotas|Salvar|Compartilhar|Avaliar|Ligar|Enviar|Sugerir|Adicionar|Ordenar|Pesquisar|Avaliações|Sobre|Visão geral|Serviços|Produtos|Ver|Abrir|Fechar|Mais|Menos|Editar|Denunciar)$/i.test(t);
                if (!skip) {
                    seenAmenities.add(t);
                    R.amenities.push(t);
                }
            }
            if (R.amenities.length >= 50) break;
        }
        if (R.amenities.length >= 50) break;
    }

    // ── Número total de fotos ─────────────────────────────────────────────────
    for (const el of document.querySelectorAll('[aria-label]')) {
        const lbl = el.getAttribute('aria-label') || '';
        const pm = lbl.match(/([\d.,]+)\s*(?:fotos?|photos?)/i);
        if (pm) {
            R.total_photos = parseInt(pm[1].replace(/[^\d]/g,''), 10) || null;
            break;
        }
    }

    // ── Foto principal da galeria (fallback melhorado) ────────────────────────
    if (!R.og_image) {
        // Tenta a foto de capa do Maps (button.aoRNLd > img)
        const heroImg = document.querySelector('button.aoRNLd img') ||
                        document.querySelector('.RZ66Rb img') ||
                        document.querySelector('img.t2cCgb') ||
                        document.querySelector('div.lu_map_section img');
        if (heroImg && heroImg.src && !heroImg.src.startsWith('data:')) {
            R.og_image = heroImg.src;
        }
    }

    // ── Link compartilhável ───────────────────────────────────────────────────
    const shareInput = document.querySelector(
        'input[value*="share.google"], input[value*="maps.app.goo.gl"], input[value*="goo.gl/maps"]'
    );
    if (shareInput) R.share_url = shareInput.value;

    // ── Status aberto/fechado ─────────────────────────────────────────────────
    // NOTA: bodyText já foi declarado com const acima — reutilizamos a variável
    if (/\baberto\b/i.test(bodyText)) R.hours.aberto_agora = true;
    else if (/\bfechado\b/i.test(bodyText)) R.hours.aberto_agora = false;

    const statusM = bodyText.match(
        /(Aberto\s*(?:24\s*horas)?|Fechado\s*(?:agora)?|Abre\s*às\s*\d{1,2}:\d{2}|Fecha\s*às\s*\d{1,2}:\d{2})/i
    );
    if (statusM) R.hours.status_atual = statusM[1].trim();

    return R;
}
"""


# ─── Substitua a função _extract_place_async inteira por esta ─────────────────

# ---------------------------------------------------------------------------
# ✅ ENRIQUECIMENTO VIA share.google — extrai Knowledge Panel completo
# ---------------------------------------------------------------------------

_JS_EXTRACT_KNOWLEDGE_PANEL = r"""
() => {
    const R = {
        phone: null, website: null, address: null, category: null,
        hours: {}, instagram: null, facebook: null, youtube: null,
        twitter: null, linkedin: null, tiktok: null,
        bio: null, rating: null, review_count: null,
        price_range: null, amenities: [], name: null,
    };

    // ── Nome da empresa ───────────────────────────────────────────────────
    // Knowledge Panel: h2.qrShPb, div[data-attrid="title"], h3.LC20lb
    const nameEl =
        document.querySelector('h2.qrShPb span') ||
        document.querySelector('[data-attrid="title"] span') ||
        document.querySelector('div.SPZz6b h2') ||
        document.querySelector('h3.LC20lb');
    if (nameEl) R.name = nameEl.textContent.trim();

    // ── Categoria ─────────────────────────────────────────────────────────
    const catEl =
        document.querySelector('[data-attrid="subtitle"] span') ||
        document.querySelector('div.wwUB2c span') ||
        document.querySelector('span.YhemCb');
    if (catEl) R.category = catEl.textContent.trim();

    // ── Telefone ──────────────────────────────────────────────────────────
    // Knowledge Panel exibe telefone em [data-attrid*="phone"] ou span com ☎
    const phoneAttrs = document.querySelectorAll('[data-attrid*="phone"] span, [data-attrid*="telefone"] span');
    for (const el of phoneAttrs) {
        const t = el.textContent.trim();
        if (/[\d\(\)\-\+\s]{7,}/.test(t) && t.length < 30) { R.phone = t; break; }
    }
    // Fallback: link tel:
    if (!R.phone) {
        const telLink = document.querySelector('a[href^="tel:"]');
        if (telLink) R.phone = telLink.getAttribute('href').replace('tel:', '').trim();
    }
    // Fallback 2: texto com padrão de telefone brasileiro
    if (!R.phone) {
        const bodyText = document.body ? document.body.innerText : '';
        const telM = bodyText.match(/\(?\d{2}\)?\s?(?:9\s?\d{4}|\d{4})[-\s]?\d{4}/);
        if (telM) R.phone = telM[0];
    }

    // ── Website ───────────────────────────────────────────────────────────
    const siteEl =
        document.querySelector('[data-attrid*="website"] a') ||
        document.querySelector('[data-attrid*="site"] a') ||
        document.querySelector('a[data-ved][href^="http"]:not([href*="google"])');
    if (siteEl) {
        const href = siteEl.getAttribute('href') || '';
        // Remove redirect do Google (/url?q=...)
        const m = href.match(/[?&]q=(https?[^&]+)/);
        R.website = m ? decodeURIComponent(m[1]) : href;
    }

    // ── Endereço ──────────────────────────────────────────────────────────
    const addrEl =
        document.querySelector('[data-attrid*="address"] span') ||
        document.querySelector('[data-attrid*="endereco"] span') ||
        document.querySelector('span.LrzXr');
    if (addrEl) R.address = addrEl.textContent.trim();

    // ── Rating e contagem de reviews ──────────────────────────────────────
    const ratingEl =
        document.querySelector('span.Aq14fc') ||
        document.querySelector('[data-attrid*="rating"] span.Aq14fc') ||
        document.querySelector('div.BHMmbe');
    if (ratingEl) {
        const t = ratingEl.textContent.trim().replace(',', '.');
        const n = parseFloat(t);
        if (!isNaN(n) && n >= 1 && n <= 5) R.rating = n;
    }
    const reviewEl =
        document.querySelector('[data-attrid*="review_count"] span') ||
        document.querySelector('span.hqzQac span') ||
        document.querySelector('a[href*="review"] span');
    if (reviewEl) {
        const t = reviewEl.textContent.replace(/\D/g, '');
        if (t) R.review_count = parseInt(t, 10);
    }

    // ── Horários de funcionamento ─────────────────────────────────────────
    // Tenta extrair da tabela de horários no Knowledge Panel
    const dayMapKP = {
        'segunda': 'seg', 'terça': 'ter', 'terca': 'ter',
        'quarta': 'qua', 'quinta': 'qui', 'sexta': 'sex',
        'sábado': 'sab', 'sabado': 'sab', 'domingo': 'dom',
        'monday': 'seg', 'tuesday': 'ter', 'wednesday': 'qua',
        'thursday': 'qui', 'friday': 'sex', 'saturday': 'sab', 'sunday': 'dom',
    };
    // Rows de horários no KP: div[data-attrid*="hours"] ou table com dias
    const hoursRows = document.querySelectorAll(
        '[data-attrid*="hours"] tr, [data-attrid*="horario"] tr, ' +
        'div.t39EBf tr, table.eK4R0e tr'
    );
    for (const row of hoursRows) {
        const cells = row.querySelectorAll('td, li');
        if (cells.length < 2) continue;
        const dayText = cells[0].textContent.trim().toLowerCase();
        const hrsText = cells[1].textContent.trim();
        let key = null;
        for (const [dayPart, abbr] of Object.entries(dayMapKP)) {
            if (dayText.startsWith(dayPart)) { key = abbr; break; }
        }
        if (!key) continue;
        const hm = hrsText.match(/(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})/);
        if (/fechado|closed/i.test(hrsText)) R.hours[key] = 'Fechado';
        else if (/24\s*horas|24\s*hours/i.test(hrsText)) R.hours[key] = '00:00–23:59';
        else if (hm) R.hours[key] = hm[1] + '–' + hm[2];
        else if (hrsText) R.hours[key] = hrsText.slice(0, 20);
    }

    // ── Bio / Descrição ───────────────────────────────────────────────────
    const bioEl =
        document.querySelector('[data-attrid*="description"] span') ||
        document.querySelector('div.kno-rdesc span');
    if (bioEl) R.bio = bioEl.textContent.trim().slice(0, 800);

    // ── Redes sociais — links presentes no Knowledge Panel ────────────────
    const allLinks = document.querySelectorAll('a[href]');
    const bad = new Set(['explore','reel','reels','p','stories','tv','accounts','tags','share']);
    for (const a of allLinks) {
        const href = a.href || '';
        // Instagram
        if (!R.instagram && /instagram\.com\//.test(href)) {
            const m = href.match(/instagram\.com\/([A-Za-z0-9._]{1,50})\/?/);
            if (m && !bad.has(m[1].toLowerCase())) R.instagram = '@' + m[1];
        }
        // Facebook
        if (!R.facebook && /(?:facebook\.com|fb\.com|fb\.me)\//.test(href)) {
            if (!/facebook\.com\/(sharer|share|login|dialog)/.test(href))
                R.facebook = href;
        }
        // YouTube
        if (!R.youtube && /youtube\.com\/(channel|c\/|@|user\/)/.test(href)) {
            R.youtube = href;
        }
        // Twitter / X
        if (!R.twitter && /(?:twitter\.com|x\.com)\//.test(href)) {
            if (!/\/(intent|share|home)/.test(href)) R.twitter = href;
        }
        // LinkedIn
        if (!R.linkedin && /linkedin\.com\//.test(href)) {
            R.linkedin = href;
        }
        // TikTok
        if (!R.tiktok && /tiktok\.com\/@/.test(href)) {
            const m = href.match(/tiktok\.com\/@([A-Za-z0-9._]+)/);
            if (m) R.tiktok = '@' + m[1];
        }
    }

    // ── Faixa de preço ────────────────────────────────────────────────────
    const allText = document.body ? document.body.innerText : '';
    const priceM = allText.match(/([$€£]{1,4})/);
    if (priceM) R.price_range = priceM[1];

    // ── Amenidades ────────────────────────────────────────────────────────
    const amenityEls = document.querySelectorAll(
        '[data-attrid*="amenities"] span, [data-attrid*="attribute"] span, ' +
        'div.bnYBrd span, div.iP2t7d span'
    );
    const seenAm = new Set();
    for (const el of amenityEls) {
        const t = el.textContent.trim();
        if (t && t.length > 3 && t.length < 80 && !seenAm.has(t)) {
            seenAm.add(t);
            R.amenities.push(t);
        }
        if (R.amenities.length >= 30) break;
    }

    return R;
}
"""

async def _enrich_from_share_url(context, share_url: str) -> dict:
    """
    Abre o link share.google/... (ou maps.app.goo.gl/...) em nova aba,
    aguarda o redirect final, extrai TODOS os dados disponíveis no
    Knowledge Panel / página de pesquisa resultante.

    Retorna dict com campos extras (pode estar vazio em caso de falha).
    """
    import asyncio
    import re

    result = {}
    page = None
    try:
        from playwright.async_api import TimeoutError as PWTimeout

        page = await context.new_page()

        # Bloqueia apenas assets pesados — precisamos de todo o conteúdo
        await page.route(
            '**/*.{woff,woff2,ttf,otf,mp4,mp3,pdf,eot}',
            lambda r: r.abort()
        )

        logger.info(f"[Maps][ShareEnrich] Abrindo: {share_url}")

        # O share.google redireciona automaticamente — wait until networkidle
        # para garantir que a página final carregou
        try:
            await page.goto(share_url, wait_until='domcontentloaded', timeout=20000)
        except PWTimeout:
            logger.warning(f"[Maps][ShareEnrich] Timeout ao abrir share_url")
            return result

        # Aguarda redirect completar (share.google → google.com/maps/place/...)
        await asyncio.sleep(3)
        final_url = page.url
        logger.info(f"[Maps][ShareEnrich] URL final após redirect: {final_url[:120]}")

        # Se caiu em página de consentimento, aceita
        try:
            from leads.scraper import _handle_consent  # tenta import relativo
        except ImportError:
            pass
        else:
            await _handle_consent(page)
            await asyncio.sleep(1)

        # Aguarda h1 ou knowledge panel
        try:
            await page.wait_for_selector('h1, h2.qrShPb, [data-attrid="title"]', timeout=10000)
        except PWTimeout:
            logger.warning("[Maps][ShareEnrich] Knowledge Panel não encontrado")
            return result

        # Scroll progressivo para forçar lazy-load de todos os campos
        _scroll_kp = """(px) => {
            const p = document.querySelector('[role="main"]') ||
                      document.querySelector('.DxyBCb') ||
                      document.body;
            if (p) p.scrollTop = px;
            else window.scrollTo(0, px);
        }"""
        for step_px in [400, 800, 1500, 2500, 4000, 7000, 99999]:
            try:
                await page.evaluate(_scroll_kp, step_px)
                await asyncio.sleep(0.5)
            except Exception:
                pass
        await asyncio.sleep(1.5)

        # Expande dropdown de horários se disponível (mesma lógica do scraper principal)
        try:
            hours_btn = None
            for sel in [
                'div.OMl5r[jsaction*="openhours"][aria-expanded="false"]',
                'div[jsaction*="openhours"][aria-expanded="false"]',
                '[jsaction*="openhours"]',
                'button[aria-label*="Outros horários"]',
                'button[aria-label*="horário"]',
            ]:
                try:
                    candidates = await page.query_selector_all(sel)
                    for c in candidates:
                        if await c.is_visible():
                            hours_btn = c
                            break
                    if hours_btn:
                        break
                except Exception:
                    continue
            if hours_btn:
                await hours_btn.click()
                await asyncio.sleep(1.5)
                logger.info("[Maps][ShareEnrich] ✓ Dropdown horários expandido")
        except Exception:
            pass

        # Extrai via JS do Knowledge Panel
        try:
            kp_data = await page.evaluate(_JS_EXTRACT_KNOWLEDGE_PANEL)
            logger.info(
                f"[Maps][ShareEnrich] ✓ KP extraído: "
                f"tel={kp_data.get('phone')} | ig={kp_data.get('instagram')} | "
                f"hrs={bool(kp_data.get('hours'))} | rating={kp_data.get('rating')}"
            )
            result.update(kp_data)
        except Exception as e:
            logger.warning(f"[Maps][ShareEnrich] Falha JS extract: {e}")

        # Se a URL final é /maps/place/, extrai horários com JS específico do Maps
        if '/maps/place/' in final_url or '/maps/search/' in final_url:
            try:
                hours_dom = await page.evaluate(r"""
() => {
    const hours = {};
    const dayMap = {
        'segunda-feira':'seg','terça-feira':'ter','terca-feira':'ter',
        'quarta-feira':'qua','quinta-feira':'qui','sexta-feira':'sex',
        'sábado':'sab','sabado':'sab','domingo':'dom'
    };
    const rows = document.querySelectorAll('table.eK4R0e tr.y0skZc, tr.y0skZc');
    for (const row of rows) {
        const cells = row.querySelectorAll('td');
        if (cells.length < 2) continue;
        const dayText = cells[0].textContent.trim().toLowerCase();
        const hrsText = cells[1].textContent.trim();
        const key = dayMap[dayText];
        if (!key) continue;
        if (/atendimento\s*24\s*horas|aberto\s*24/i.test(hrsText)) {
            hours[key] = '00:00–23:59';
        } else if (/fechado|closed/i.test(hrsText)) {
            hours[key] = 'Fechado';
        } else {
            const hm = hrsText.match(/(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})/);
            if (hm) hours[key] = hm[1] + '–' + hm[2];
            else if (hrsText.length > 3) hours[key] = hrsText.slice(0, 20);
        }
    }
    const openEl = document.querySelector('[class*="ZjTjCd"], [class*="o0Svhf"]');
    if (openEl) {
        const txt = openEl.textContent.trim();
        if (txt) hours.status_atual = txt.slice(0, 80);
        hours.aberto_agora = !/fechado/i.test(txt);
    }
    return hours;
}
                """)
                if hours_dom and len([k for k in hours_dom if k not in ('status_atual', 'aberto_agora')]) > 0:
                    result['hours'] = hours_dom
                    logger.info(f"[Maps][ShareEnrich] ✓ Horários do DOM Maps: {list(hours_dom.keys())}")
            except Exception:
                pass

            # Extrai reviews da página do Maps se disponível
            try:
                reviews_extra = await page.evaluate(r"""
() => {
    const reviews = [];
    const seen = new Set();
    const containers = [
        ...document.querySelectorAll('[data-review-id]'),
        ...document.querySelectorAll('div.jftiEf'),
    ];
    for (const c of containers) {
        if (reviews.length >= 10) break;
        const rev = {};
        const authorEl = c.querySelector('div[class*="d4r55"]') || c.querySelector('.d4r55');
        if (authorEl) rev.author = authorEl.textContent.trim();
        const ratingEl = c.querySelector('[aria-label*="estrela"]') || c.querySelector('[aria-label*="star"]');
        if (ratingEl) {
            const m = (ratingEl.getAttribute('aria-label') || '').match(/(\d)/);
            if (m) rev.rating = parseInt(m[1]);
        }
        const dateEl = c.querySelector('span[class*="rsqaWe"]') || c.querySelector('span[class*="xRkPPb"]');
        if (dateEl) rev.date = dateEl.textContent.trim();
        const textEl = c.querySelector('span[class*="wiI7pd"]');
        if (textEl) rev.text = textEl.textContent.trim().slice(0, 1000);
        if (!rev.author && !rev.text && !rev.rating) continue;
        const key = [(rev.author||'').toLowerCase(), (rev.date||''), (rev.text||'').slice(0,60)].join('|');
        if (seen.has(key)) continue;
        seen.add(key);
        reviews.push(rev);
    }
    return reviews;
}
                """)
                if reviews_extra:
                    result['recent_reviews_extra'] = reviews_extra
                    logger.info(f"[Maps][ShareEnrich] ✓ {len(reviews_extra)} reviews extras")
            except Exception:
                pass

        # Extrai og:image da página de resultado
        try:
            og_img = await page.evaluate("""
() => {
    const og = document.querySelector('meta[property="og:image"]');
    if (og) return og.getAttribute('content');
    const img = document.querySelector('button.aoRNLd img') ||
                document.querySelector('.RZ66Rb img') ||
                document.querySelector('img.t2cCgb');
    return img && img.src && !img.src.startsWith('data:') ? img.src : null;
}
            """)
            if og_img:
                result['og_image_extra'] = og_img
        except Exception:
            pass

    except Exception as e:
        logger.warning(f"[Maps][ShareEnrich] Erro geral: {e}")
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass

    return result


async def _extract_place_async(
    context,
    url: str,
    city: str,
    only_without_website: bool = False,
    min_rating: float | None = None,
    min_reviews: int | None = None,
    only_with_instagram: bool = False,
    only_with_facebook: bool = False,
) -> dict | None:
    """
    Extrai TODOS os dados de um lugar via Playwright (JS evaluate).
    v9.1: usa _JS_EXTRACT_ALL para capturar dados direto do DOM vivo —
    muito mais confiável que BeautifulSoup no HTML estático.
    """
    import asyncio
    import re
    import os
    import urllib.parse
    from bs4 import BeautifulSoup

    page = None
    try:
        from playwright.async_api import TimeoutError as PWTimeout

        page = await context.new_page()

        # NÃO bloqueamos imagens aqui — são necessárias para og:image e fotos
        # Bloqueamos apenas fontes/vídeos pesados (não afetam dados do Maps)
        await page.route(
            '**/*.{woff,woff2,ttf,otf,mp4,mp3,pdf,eot}',
            lambda r: r.abort()
        )
        # Bloqueia trackers e analytics que podem atrasar o carregamento
        await page.route(
            '**/analytics.js',
            lambda r: r.abort()
        )

        await page.goto(url, wait_until='domcontentloaded', timeout=30000)

        # Aguarda h1 (nome do lugar)
        try:
            await page.wait_for_selector('h1', timeout=10000)
        except PWTimeout:
            logger.warning(f"[Maps] h1 não encontrado em: {url[:80]}")
            await page.close()
            return None

        await asyncio.sleep(2)

        # ── Scroll progressivo para carregar conteúdo lazy ────────────────────
        # v11: múltiplos seletores de container + pausa maior em cada passo para
        # forçar lazy-load completo: atributos, amenidades, popular times, fotos,
        # horários, seção "Resultados da Web" e todos os campos do box lateral.
        _scroll_script = """(scrollTop) => {
            // O painel lateral do Maps usa vários possíveis containers de scroll
            const containers = [
                document.querySelector('div[role="main"]'),
                document.querySelector('.DxyBCb'),
                document.querySelector('.bJzME'),       // painel lateral v2024
                document.querySelector('.siAUzd'),      // painel lateral alternativo
                document.querySelector('[jsrenderer="lutinne"]'),
                document.querySelector('.TIHn2'),
                document.querySelector('[aria-label][role="region"]'),
            ];
            const p = containers.find(c => c && c.scrollHeight > window.innerHeight);
            if (p) {
                p.scrollTop = scrollTop;
            } else {
                window.scrollTo(0, scrollTop);
            }
        }"""
        # Passos progressivos com pausa maior: dá tempo para cada seção renderizar
        scroll_steps = [200, 500, 900, 1400, 2000, 2800, 3800, 5000, 6500, 8500, 12000, 99999]
        for step_px in scroll_steps:
            try:
                await page.evaluate(_scroll_script, step_px)
                await asyncio.sleep(0.8)  # pausa maior para lazy-load
            except Exception:
                pass
        # Aguarda carregamento completo após scroll total
        await asyncio.sleep(1.5)
        # Scroll de volta ao topo para garantir que h1 e categoria estejam visíveis
        try:
            await page.evaluate(
                """() => {
                    const containers = [
                        document.querySelector('div[role="main"]'),
                        document.querySelector('.DxyBCb'),
                        document.querySelector('.bJzME'),
                        document.querySelector('.siAUzd'),
                    ];
                    const p = containers.find(c => c && c.scrollHeight > window.innerHeight);
                    if (p) p.scrollTop = 0;
                    else window.scrollTo(0, 0);
                }"""
            )
            await asyncio.sleep(0.5)
        except Exception:
            pass

        # Aguarda reviews e horários
        try:
            await page.wait_for_selector(
                '[data-review-id], div[jsaction*="review"], [class*="jftiEf"]',
                timeout=5000
            )
        except Exception:
            pass

        # ── Expande dropdown de horários ─────────────────────────────────────
        # Seletores baseados no HTML real do Google Maps (ficha completa):
        # O elemento é div.OMl5r.hH0dDd com jsaction*="openhours" e aria-expanded="false"
        try:
            hours_btn = None
            hours_selectors = [
                # Seletor primário — div com jsaction de openhours não expandido
                'div.OMl5r[jsaction*="openhours"][aria-expanded="false"]',
                'div.OMl5r[aria-expanded="false"]',
                # Fallbacks por jsaction
                'div[jsaction*="openhours"][aria-expanded="false"]',
                '[jsaction*="openhours.wfvdle"]',
                '[jsaction*="openhours"]',
                # Por aria
                'button[aria-label*="Outros horários"]',
                'button[aria-label*="horário"]',
                # Estrutura do container OqCZI (div de horários)
                'div.OqCZI .OMl5r',
                'div.OqCZI [role="button"]',
            ]
            for sel in hours_selectors:
                try:
                    candidates = await page.query_selector_all(sel)
                    for candidate in candidates:
                        if await candidate.is_visible():
                            hours_btn = candidate
                            logger.info(f"[Maps][v9] Botão horários via: {sel!r}")
                            break
                    if hours_btn:
                        break
                except Exception:
                    continue

            if hours_btn:
                await hours_btn.click()
                await asyncio.sleep(2.0)
                logger.info("[Maps][v9] ✓ Dropdown de horários expandido")
                try:
                    await page.wait_for_selector(
                        'table.eK4R0e, tr.y0skZc, div[class*="t39EBf"] tr',
                        timeout=5000
                    )
                    logger.info("[Maps][v9] ✓ Tabela de horários carregada")
                except Exception:
                    # Mesmo sem confirmar, o clique pode ter funcionado
                    await asyncio.sleep(1.0)
            else:
                logger.info("[Maps][v9] Botão de horários não encontrado (pode já estar expandido ou ausente)")
        except Exception as e:
            logger.debug(f"[Maps][v9] Erro ao expandir horários: {e}")

        # ── Navega para aba "Sobre" para capturar atributos completos ─────────
        # IMPORTANTE: capturamos os atributos DA ABA SOBRE diretamente via JS
        # enquanto estamos nela, sem voltar para "Visão geral" entre as etapas.
        # O nome do lugar é capturado ANTES de qualquer navegação de aba.
        about_amenities = []  # inicializado aqui para garantir escopo
        try:
            about_tab = None
            about_selectors = [
                'button[aria-label="Sobre"]',
                'button[data-tab-index="3"]',
                'button.hh2c6:has-text("Sobre")',
                '[role="tab"]:has-text("Sobre")',
            ]
            for sel in about_selectors:
                try:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        about_tab = btn
                        logger.info(f"[Maps][v11] Aba Sobre encontrada: {sel!r}")
                        break
                except Exception:
                    continue

            if about_tab:
                await about_tab.click()
                await asyncio.sleep(2.5)
                # Scroll dentro da aba Sobre
                for scroll_px in [400, 800, 1600, 3000, 99999]:
                    try:
                        await page.evaluate("""(px) => {
                            const containers = [
                                document.querySelector('div[role="main"]'),
                                document.querySelector('.DxyBCb'),
                                document.querySelector('.bJzME'),
                            ];
                            const p = containers.find(c => c && c.scrollHeight > window.innerHeight);
                            if (p) p.scrollTop = px;
                        }""", scroll_px)
                        await asyncio.sleep(0.4)
                    except Exception:
                        pass
                await asyncio.sleep(0.8)

                # Extrai amenidades diretamente enquanto está na aba Sobre
                try:
                    about_amenities = await page.evaluate("""
() => {
    const items = [];
    const seen = new Set();
    const selectors = [
        'div.iP2t7d span', 'div.E0DTEd span', 'li.hpLkke span',
        'div.sSHqwe span', 'div.lX8Tbe span', 'div.ekb8yd span',
        'div.Io6YTe', 'ul.ZjVtHb li',
        '[aria-label*="Aceita"]','[aria-label*="Wi-Fi"]',
        '[aria-label*="Acessív"]','[aria-label*="Estacionamento"]',
        '[aria-label*="Pagamento"]','[aria-label*="Refeição"]',
        '[aria-label*="Serviço"]','[aria-label*="Crianças"]',
        '[aria-label*="Animal"]','[aria-label*="LGBTQ"]',
    ];
    const skipRe = /^(Rotas|Salvar|Compartilhar|Avaliar|Ligar|Enviar|Sugerir|Adicionar|Ordenar|Pesquisar|Avaliações|Sobre|Visão geral|Serviços|Produtos|Ver|Abrir|Fechar|Mais|Menos|Editar|Denunciar)$/i;
    for (const sel of selectors) {
        for (const el of document.querySelectorAll(sel)) {
            const t = (el.getAttribute('aria-label') || el.textContent || '').trim().replace(/\\s+/g,' ');
            if (t && t.length > 3 && t.length < 120 && !seen.has(t) && !skipRe.test(t)) {
                seen.add(t);
                items.push(t);
            }
            if (items.length >= 50) break;
        }
        if (items.length >= 50) break;
    }
    return items;
}
                    """)
                    if about_amenities:
                        logger.info(f"[Maps][v11] ✓ {len(about_amenities)} atributos capturados na aba Sobre")
                except Exception as ae:
                    logger.debug(f"[Maps][v11] Erro ao extrair atributos da aba Sobre: {ae}")

                logger.info("[Maps][v11] ✓ Aba Sobre visitada e scrollada")

                # Volta para "Visão geral" e aguarda h1 correto carregar
                try:
                    overview_tab = await page.query_selector(
                        'button[aria-label="Visão geral"], '
                        'button[data-tab-index="0"], '
                        '[role="tab"]:has-text("Visão geral")'
                    )
                    if overview_tab:
                        await overview_tab.click()
                        # Aguarda até o h1 não ser mais "Horários" ou texto de aba
                        import asyncio as _aio
                        for _ in range(20):
                            await _aio.sleep(0.3)
                            try:
                                h1_text = await page.evaluate(
                                    "() => { const h = document.querySelector('h1'); return h ? h.textContent.trim() : ''; }"
                                )
                                bad_names = {'horários', 'avaliações', 'sobre', 'visão geral',
                                             'horarios', 'avaliacoes', 'servicos', 'serviços',
                                             'fotos', 'produtos'}
                                if h1_text and h1_text.lower() not in bad_names and len(h1_text) > 2:
                                    logger.info(f"[Maps][v11] ✓ h1 estável após retorno: '{h1_text}'")
                                    break
                            except Exception:
                                pass
                except Exception:
                    await asyncio.sleep(2.0)
            else:
                logger.info("[Maps][v11] Aba Sobre não encontrada — atributos via DOM principal")
        except Exception as e:
            logger.debug(f"[Maps][v11] Erro ao acessar aba Sobre: {e}")

        # ── Expande textos de reviews truncados ───────────────────────────────
        try:
            more_btns = await page.query_selector_all(
                'button[aria-label*="Ver mais"], button.w8nwRe, '
                'button[jsaction*="reviewfulltext"], button[class*="w8nwRe"], '
                'button[aria-label*="Mais"], .review-more-link'
            )
            for btn in more_btns[:20]:
                try:
                    if await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.15)
                except Exception:
                    pass
        except Exception:
            pass

        await asyncio.sleep(0.5)

        # ── Captura compartilhamento (share URL) ──────────────────────────────
        share_url = None
        try:
            share_btn = (
                await page.query_selector('button[data-value="Compartilhar"]') or
                await page.query_selector('button[aria-label*="ompartilhar"]')
            )
            if share_btn:
                await share_btn.click()
                await asyncio.sleep(0.8)
                share_input = await page.query_selector(
                    'input[value*="share.google"], input[value*="maps.app.goo.gl"], input[value*="goo.gl/maps"]'
                )
                if share_input:
                    share_url = await share_input.get_attribute('value')
                try:
                    await page.keyboard.press('Escape')
                except Exception:
                    pass
        except Exception:
            pass

        # ── Extração JS unificada — captura tudo direto do DOM vivo ──────────
        tiktok_val = None  # inicializado aqui para evitar NameError no bloco enrich_data
        try:
            js_data = await page.evaluate(_JS_EXTRACT_ALL)
        except Exception as e:
            logger.warning(f"[Maps] Falha no JS extract: {e}")
            js_data = {}

        # ── Extração de horários via JS (direto do DOM expandido) ───────────
        # Lê a tabela APÓS o dropdown ter sido expandido pelo Playwright
        hours_from_js = await page.evaluate(r"""
() => {
    const hours = {};
    const dayMap = {
        'segunda-feira':'seg','terça-feira':'ter','terca-feira':'ter',
        'quarta-feira':'qua','quinta-feira':'qui','sexta-feira':'sex',
        'sábado':'sab','sabado':'sab','domingo':'dom'
    };

    // Estratégia 1: tabela eK4R0e com linhas y0skZc (dropdown expandido)
    const rows = document.querySelectorAll('table.eK4R0e tr.y0skZc, tr.y0skZc');
    for (const row of rows) {
        const cells = row.querySelectorAll('td');
        if (cells.length < 2) continue;
        const dayText = cells[0].textContent.trim().toLowerCase();
        const hrsText = cells[1].textContent.trim();
        const key = dayMap[dayText];
        if (!key) continue;
        if (/atendimento\s*24\s*horas|aberto\s*24/i.test(hrsText)) {
            hours[key] = '00:00–23:59';
        } else if (/fechado|closed/i.test(hrsText)) {
            hours[key] = 'Fechado';
        } else {
            // Suporte a 2 períodos no mesmo dia: "08:00–11:30 / 14:00–17:00"
            const allPeriods = [...hrsText.matchAll(/(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})/g)];
            if (allPeriods.length >= 2) {
                hours[key] = allPeriods.map(m => m[1] + '–' + m[2]).join(' / ');
            } else if (allPeriods.length === 1) {
                hours[key] = allPeriods[0][1] + '–' + allPeriods[0][2];
            } else if (hrsText.length > 3) {
                hours[key] = hrsText.slice(0, 30);
            }
        }
    }

    // Estratégia 2: aria-label individuais "dia, HH:MM–HH:MM" (tr com data-value)
    if (Object.keys(hours).length < 3) {
        const btns = document.querySelectorAll('button.mWUh3d[data-value]');
        for (const btn of btns) {
            const val = btn.getAttribute('data-value') || '';
            const m = val.match(/^([^,]+),\s*(.+)$/);
            if (!m) continue;
            const key = dayMap[m[1].trim().toLowerCase()];
            if (!key || hours[key]) continue;
            const rawHrs = m[2].trim();
            if (/atendimento\s*24\s*horas|aberto\s*24/i.test(rawHrs)) {
                hours[key] = '00:00–23:59';
            } else if (/fechado|closed/i.test(rawHrs)) {
                hours[key] = 'Fechado';
            } else {
                // Suporte a 2 períodos: "08:00–11:30 / 14:00–17:00"
                const allP = [...rawHrs.matchAll(/(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})/g)];
                if (allP.length >= 2) hours[key] = allP.map(p => p[1]+'–'+p[2]).join(' / ');
                else if (allP.length === 1) hours[key] = allP[0][1] + '–' + allP[0][2];
            }
        }
    }

    // Estratégia 3: divs com jsaction openhours já expandido — li ou tr dentro do container
    if (Object.keys(hours).length < 3) {
        const hoursContainer = document.querySelector(
            'div.OqCZI, div[jsaction*="openhours"]'
        );
        if (hoursContainer) {
            const liRows = hoursContainer.querySelectorAll('li, tr');
            for (const row of liRows) {
                const txt = row.textContent.trim().toLowerCase();
                let key = null;
                for (const [dayPart, abbr] of Object.entries(dayMap)) {
                    if (txt.startsWith(dayPart)) { key = abbr; break; }
                }
                if (!key || hours[key]) continue;
                const allP = [...txt.matchAll(/(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})/g)];
                if (/atendimento\s*24\s*horas|aberto\s*24/i.test(txt)) {
                    hours[key] = '00:00–23:59';
                } else if (/fechado|closed/i.test(txt)) {
                    hours[key] = 'Fechado';
                } else if (allP.length >= 2) {
                    hours[key] = allP.map(p => p[1]+'–'+p[2]).join(' / ');
                } else if (allP.length === 1) {
                    hours[key] = allP[0][1] + '–' + allP[0][2];
                }
            }
        }
    }

    // Status atual (aberto agora / fechado agora)
    const openEl = document.querySelector('[class*="ZjTjCd"], [class*="o0Svhf"]');
    if (openEl) {
        const txt = openEl.textContent.trim();
        if (txt) hours.status_atual = txt.slice(0, 80);
        hours.aberto_agora = !/fechado/i.test(txt);
    }

    return hours;
}
        """)
        if hours_from_js and len(hours_from_js) > 1:
            logger.info(f"[Maps][v9] ✓ Horários via JS DOM: {hours_from_js}")

        # ── Extração de reviews via JS (mais confiável que BS4) ───────────────
        reviews_js = await page.evaluate("""
() => {
    const reviews = [];
    const seen = new Set();

    // Containers de review
    const containers = [
        ...document.querySelectorAll('[data-review-id]'),
        ...document.querySelectorAll('div.jftiEf'),
    ];

    for (const c of containers) {
        if (reviews.length >= 10) break;
        const rev = {};

        // Autor
        const authorEl = c.querySelector('div[class*="d4r55"]') ||
                         c.querySelector('.d4r55') ||
                         c.querySelector('button.al6Kxe div');
        if (authorEl) rev.author = authorEl.textContent.trim();

        // Badge
        const badgeEl = c.querySelector('div[class*="RfnDt"]') || c.querySelector('.RfnDt');
        if (badgeEl) rev.author_badge = badgeEl.textContent.trim();

        // Rating
        const ratingEl = c.querySelector('[aria-label*="estrela"]') ||
                         c.querySelector('[aria-label*="star"]');
        if (ratingEl) {
            const m = (ratingEl.getAttribute('aria-label') || '').match(/(\\d)/);
            if (m) rev.rating = parseInt(m[1]);
        }

        // Data
        const dateEl = c.querySelector('span[class*="rsqaWe"]') ||
                       c.querySelector('span[class*="xRkPPb"]');
        if (dateEl) rev.date = dateEl.textContent.trim();

        // Texto completo
        const textEl = c.querySelector('span[class*="wiI7pd"]') ||
                       c.querySelector('[class*="MyEned"] span') ||
                       c.querySelector('div[class*="review-full-text"]');
        if (textEl) rev.text = textEl.textContent.trim().slice(0, 1000);

        // Resposta do proprietário
        const ownerEl = c.querySelector('div[class*="CDe7pd"]') || c.querySelector('.CDe7pd');
        if (ownerEl) {
            const ownerText = ownerEl.querySelector('span[class*="wiI7pd"]');
            const ownerDate = ownerEl.querySelector('span[class*="DZSIDd"]');
            if (ownerText) rev.owner_reply = ownerText.textContent.trim().slice(0, 500);
            if (ownerDate) rev.owner_reply_date = ownerDate.textContent.trim();
        }

        if (!rev.author && !rev.text && !rev.rating) continue;

        const key = [(rev.author||'').toLowerCase(), (rev.date||''), (rev.text||'').slice(0,60)].join('|');
        if (seen.has(key)) continue;
        seen.add(key);
        reviews.push(rev);
    }
    return reviews;
}
        """)

        maps_canonical_url = page.url if '/maps/place/' in page.url else url

        # ── Screenshot de diagnóstico ─────────────────────────────────────────
        try:
            import time as _time
            import re as _re
            screenshot_dir = _get_screenshot_dir()
            page_title = await page.title()
            safe_title = _re.sub(r'[^\w\-]', '_', page_title)[:60].strip('_') or 'lead'
            ts = int(_time.time())
            shot_path = os.path.join(screenshot_dir, f"lead_{safe_title}_{ts}.png")
            await page.screenshot(path=shot_path, full_page=True)
            logger.info(f"[Maps:screenshot] ✓ Salvo: {shot_path}")
        except Exception as _se:
            logger.debug(f"[Maps:screenshot] Falha: {_se}")

        # ── "Resultados da Web" iframe (redes sociais adicionais) ─────────────
        # O iframe /search?pcl=lp contém links do site oficial da empresa,
        # Instagram, Facebook, LinkedIn etc. É a fonte mais confiável para redes sociais.
        web_results_social = {}
        try:
            # Scroll agressivo até o fim para forçar carregamento do iframe
            for scroll_px in [3000, 6000, 99999]:
                await page.evaluate(
                    """(px) => {
                        const p = document.querySelector('[role="main"]') ||
                                  document.querySelector('.DxyBCb') ||
                                  document.body;
                        if (p) p.scrollTop = px;
                    }""",
                    scroll_px
                )
                await asyncio.sleep(0.8)

            # Aguarda o iframe aparecer com timeout generoso
            iframe_appeared = False
            for iframe_sel in [
                'iframe.rvN3ke',
                'iframe[src*="pcl=lp"]',
                'iframe[src*="ibp=gwp"]',
                'iframe[src*="/search?"]',
            ]:
                try:
                    await page.wait_for_selector(iframe_sel, timeout=4000)
                    iframe_appeared = True
                    logger.info(f"[Maps][v9] iframe detectado via: {iframe_sel!r}")
                    break
                except Exception:
                    continue

            if iframe_appeared:
                await asyncio.sleep(2.5)  # Aguarda iframe carregar completamente

            # Método 1: lê content() de cada frame
            for frame in page.frames:
                frame_url = frame.url or ''
                if '/search?' in frame_url or 'ibp=gwp' in frame_url or 'pcl=lp' in frame_url:
                    try:
                        # Aguarda o frame ter conteúdo
                        await asyncio.sleep(1.0)
                        web_html = await frame.content()
                        if web_html and len(web_html) > 500:
                            web_results_social = _extract_web_results_full(web_html)
                            if web_results_social:
                                logger.info(f"[Maps][v9] ✓ iframe social (frame.content): {web_results_social}")
                                break
                        # Se HTML muito curto, tenta evaluate
                        web_html2 = await frame.evaluate("document.documentElement.outerHTML")
                        if web_html2 and len(web_html2) > 500:
                            web_results_social = _extract_web_results_full(web_html2)
                            if web_results_social:
                                logger.info(f"[Maps][v9] ✓ iframe social (frame.evaluate): {web_results_social}")
                                break
                    except Exception as fe:
                        logger.debug(f"[Maps][v9] frame.content erro: {fe}")
                    break

            # Método 2: lê o src do iframe e busca com nova aba Playwright
            if not web_results_social:
                try:
                    iframe_src = await page.evaluate("""
                        () => {
                            const f = document.querySelector('iframe.rvN3ke, iframe[src*="pcl=lp"], iframe[src*="ibp=gwp"]');
                            return f ? f.src : null;
                        }
                    """)
                    if iframe_src and iframe_src.startswith('http'):
                        logger.info(f"[Maps][v9] Tentando iframe via nova aba: {iframe_src[:100]}")
                        iframe_page = await context.new_page()
                        try:
                            await iframe_page.goto(iframe_src, wait_until='domcontentloaded', timeout=15000)
                            await asyncio.sleep(2)
                            iframe_html_full = await iframe_page.content()
                            web_results_social = _extract_web_results_full(iframe_html_full)
                            if web_results_social:
                                logger.info(f"[Maps][v9] ✓ iframe social (nova aba): {web_results_social}")
                        except Exception as ipe:
                            logger.debug(f"[Maps][v9] iframe nova aba erro: {ipe}")
                        finally:
                            try:
                                await iframe_page.close()
                            except Exception:
                                pass
                except Exception as ie:
                    logger.debug(f"[Maps][v9] iframe src read erro: {ie}")

            if not web_results_social:
                logger.info("[Maps][v9] iframe 'Resultados da Web' sem dados de redes sociais")
        except Exception as e:
            logger.debug(f"[Maps][v9] iframe error: {e}")

        await page.close()

        # ── Monta dict final combinando JS extract + iframe social ────────────
        if not js_data or not js_data.get('name'):
            return None

        # Valida que o nome não é um nome de aba do Maps
        _raw_name_check = js_data.get('name', '').strip()
        _bad_tab_names = {
            'horários', 'avaliações', 'sobre', 'visão geral', 'visao geral',
            'horarios', 'avaliacoes', 'servicos', 'serviços', 'fotos',
            'produtos', 'menu', 'reservar', 'ligar',
        }
        if _raw_name_check.lower() in _bad_tab_names:
            logger.warning(f"[Maps][v11] Nome inválido '{_raw_name_check}' (h1 capturado como aba) — descartando")
            return None

        phone_raw = js_data.get('phone')
        normalized = normalize_phone(phone_raw) if phone_raw else None

        # Detecta tipo do website
        raw_website = js_data.get('website')
        website_type = detect_website_type(raw_website)

        # Merge das redes sociais: JS > iframe > None
        def _merge(js_val, iframe_val):
            return js_val or iframe_val or None

        instagram = _merge(js_data.get('instagram'), web_results_social.get('instagram'))
        facebook  = _merge(js_data.get('facebook'),  web_results_social.get('facebook'))
        youtube   = _merge(js_data.get('youtube'),   web_results_social.get('youtube'))
        twitter   = _merge(js_data.get('twitter'),   web_results_social.get('twitter'))
        linkedin  = _merge(js_data.get('linkedin'),  web_results_social.get('linkedin'))

        # Normaliza handles de instagram
        if instagram and not instagram.startswith('@'):
            instagram = '@' + instagram

        # Filtra handles ruins do instagram
        if instagram:
            bad_ig = {'explore', 'reel', 'reels', 'p', 'stories', 'tv', 'accounts', 'tags', 'share'}
            handle = instagram.lstrip('@').lower()
            if handle in bad_ig:
                instagram = None

        # Resolve website que é na verdade uma rede social e atualiza variáveis locais
        if raw_website:
            _site_resolve_tmp = {
                'instagram': instagram, 'facebook': facebook,
                'normalized_phone': normalized,
                'website': raw_website,
                'website_detected_type': website_type,
            }
            _resolve_social_from_website(raw_website, _site_resolve_tmp)
            # Propaga os valores atualizados de volta para as variáveis locais
            if not instagram and _site_resolve_tmp.get('instagram'):
                instagram = _site_resolve_tmp['instagram']
            if not facebook and _site_resolve_tmp.get('facebook'):
                facebook = _site_resolve_tmp['facebook']
            if not normalized and _site_resolve_tmp.get('normalized_phone'):
                normalized = _site_resolve_tmp['normalized_phone']
            raw_website = _site_resolve_tmp.get('website')
            website_type = _site_resolve_tmp.get('website_detected_type', website_type)

        # Filtros aplicados
        if only_without_website and raw_website and website_type == 'website':
            logger.info(f"[Maps][Filtro] '{js_data.get('name','')}' descartado — tem website ({raw_website[:50]})")
            return None
        if only_with_instagram and not instagram:
            logger.info(f"[Maps][Filtro] '{js_data.get('name','')}' descartado — sem Instagram")
            return None
        if only_with_facebook and not facebook:
            logger.info(f"[Maps][Filtro] '{js_data.get('name','')}' descartado — sem Facebook")
            return None

        # Prioridade horários: DOM JS (mais preciso) > aria-label JS > fallback vazio
        # hours_from_js vem da tabela expandida no DOM (mais confiável)
        hours_raw = {}
        if hours_from_js and len([k for k in hours_from_js if k not in ('status_atual','aberto_agora')]) > 0:
            hours_raw = hours_from_js
            logger.info(f"[Maps][v9] Usando horários do DOM JS: {list(hours_raw.keys())}")
        elif js_data.get('hours'):
            hours_raw = js_data.get('hours')
            logger.info(f"[Maps][v9] Usando horários do aria-label JS: {list(hours_raw.keys())}")

        _KEY_MAP = {
            'seg': 'seg', 'ter': 'ter', 'qua': 'qua',
            'qui': 'qui', 'sex': 'sex', 'sab': 'sab', 'dom': 'dom',
        }
        hours_clean = {}
        for k, v in hours_raw.items():
            if k in _KEY_MAP:
                hours_clean[_KEY_MAP[k]] = v
            else:
                hours_clean[k] = v  # status_atual, aberto_agora

        # Garante que status_atual e aberto_agora venham de hours_from_js se disponível
        if hours_from_js:
            if 'status_atual' in hours_from_js and 'status_atual' not in hours_clean:
                hours_clean['status_atual'] = hours_from_js['status_atual']
            if 'aberto_agora' in hours_from_js and 'aberto_agora' not in hours_clean:
                hours_clean['aberto_agora'] = hours_from_js['aberto_agora']

        # Rating e review_count
        rating = js_data.get('rating')
        review_count = js_data.get('review_count') or 0

        if min_rating is not None and (not rating or rating < min_rating):
            return None
        if min_reviews is not None and review_count < min_reviews:
            return None

        # Foto de perfil — usa og:image do Maps, ou busca no Instagram
        profile_pic = js_data.get('og_image')
        if instagram and not profile_pic:
            profile_pic = fetch_instagram_profile_pic(instagram)

        share_final = share_url or js_data.get('share_url') or _extract_share_url(
            BeautifulSoup('<html/>', 'html.parser'), ''
        )

        # ── ENRIQUECIMENTO VIA share.google ───────────────────────────────────
        # Abre o link de compartilhamento em nova aba para extrair dados
        # completos do Knowledge Panel / página de busca — muito mais rico
        # que o box lateral do Maps.
        enrich_data = {}
        if share_final and share_final.startswith('http'):
            try:
                enrich_data = await _enrich_from_share_url(context, share_final)
                logger.info(
                    f"[Maps][ShareEnrich] Merge: "
                    f"tel={enrich_data.get('phone')} | "
                    f"ig={enrich_data.get('instagram')} | "
                    f"site={enrich_data.get('website')} | "
                    f"hrs={bool(enrich_data.get('hours'))} | "
                    f"rating={enrich_data.get('rating')}"
                )
            except Exception as _ee:
                logger.warning(f"[Maps][ShareEnrich] Erro no enriquecimento: {_ee}")

        def _best(primary, secondary):
            """Retorna primary se não-vazio, senão secondary."""
            if primary is not None and primary != '' and primary != [] and primary != {}:
                return primary
            return secondary

        # Merge: dados do scrape principal têm prioridade;
        # enrich_data preenche campos que faltaram
        if enrich_data:
            phone_raw   = _best(phone_raw,   enrich_data.get('phone'))
            raw_website = _best(raw_website, enrich_data.get('website'))

            # Recalcula normalized_phone se veio do enrich
            if not normalized and phone_raw:
                normalized = normalize_phone(phone_raw)

            # Recalcula tipo do website se veio do enrich
            if not (js_data.get('website')) and raw_website:
                website_type = detect_website_type(raw_website)

            # Redes sociais: preenche lacunas
            instagram = _best(instagram, enrich_data.get('instagram'))
            facebook  = _best(facebook,  enrich_data.get('facebook'))
            youtube   = _best(youtube,   enrich_data.get('youtube'))
            twitter   = _best(twitter,   enrich_data.get('twitter'))
            linkedin  = _best(linkedin,  enrich_data.get('linkedin'))
            if not tiktok_val:
                tiktok_val = enrich_data.get('tiktok')

            # Horários: se o scrape principal não capturou, usa do enrich
            if not hours_clean and enrich_data.get('hours'):
                _KEY_MAP_E = {
                    'seg':'seg','ter':'ter','qua':'qua',
                    'qui':'qui','sex':'sex','sab':'sab','dom':'dom',
                }
                for k, v in enrich_data['hours'].items():
                    if k in _KEY_MAP_E:
                        hours_clean[_KEY_MAP_E[k]] = v
                    else:
                        hours_clean[k] = v
                logger.info(f"[Maps][ShareEnrich] Horários preenchidos via enrich: {list(hours_clean.keys())}")

            # Reviews extras
            if not reviews_js and enrich_data.get('recent_reviews_extra'):
                reviews_js = enrich_data['recent_reviews_extra']
                logger.info(f"[Maps][ShareEnrich] Reviews preenchidas via enrich: {len(reviews_js)}")

            # Foto de perfil
            if not profile_pic and enrich_data.get('og_image_extra'):
                profile_pic = enrich_data['og_image_extra']

            # Rating e review_count: usa o maior valor (mais confiável)
            enrich_rating = enrich_data.get('rating')
            enrich_rc     = enrich_data.get('review_count')
            if enrich_rating and (not rating or enrich_rating > rating):
                rating = enrich_rating
            if enrich_rc and (not review_count or enrich_rc > review_count):
                review_count = enrich_rc

            # Bio
            if not (js_data.get('bio') or '').strip() and enrich_data.get('bio'):
                js_data['bio'] = enrich_data['bio']

            # Amenidades
            if not js_data.get('amenities') and enrich_data.get('amenities'):
                js_data['amenities'] = enrich_data['amenities']

            # Price range
            if not js_data.get('price_range') and enrich_data.get('price_range'):
                js_data['price_range'] = enrich_data['price_range']

            # Normaliza instagram do enrich
            if instagram and not instagram.startswith('@'):
                instagram = '@' + instagram
            # Filtra handles ruins
            if instagram:
                bad_ig = {'explore','reel','reels','p','stories','tv','accounts','tags','share'}
                if instagram.lstrip('@').lower() in bad_ig:
                    instagram = None

        # v10: whatsapp_link preenche phone se estiver vazio
        whatsapp_link = js_data.get('whatsapp_link')
        if whatsapp_link and not normalized:
            normalized = whatsapp_link if whatsapp_link.startswith('55') else f"55{whatsapp_link}"
        if whatsapp_link and not phone_raw:
            digits = whatsapp_link
            if len(digits) >= 10:
                phone_raw = f"({digits[-10:-8]}) {digits[-8:-4]}-{digits[-4:]}"

        # v10: tiktok — usa valor enriquecido de enrich_data se disponível, senão do JS principal
        if not tiktok_val:
            tiktok_val = js_data.get('tiktok')
        _am_js = js_data.get('amenities') or []
        _am_about = about_amenities or []
        _am_seen = set()
        _am_merged = []
        for _item in (_am_about + _am_js):  # Sobre tem prioridade (mais preciso)
            if _item and _item not in _am_seen:
                _am_seen.add(_item)
                _am_merged.append(_item)

        # ── Valida nome: não pode ser nome de aba ─────────────────────────────
        _raw_name = js_data.get('name', '').strip()
        _bad_names = {
            'horários', 'avaliações', 'sobre', 'visão geral', 'visao geral',
            'horarios', 'avaliacoes', 'servicos', 'serviços', 'fotos',
            'produtos', 'menu', 'reservar', 'ligar',
        }
        if _raw_name.lower() in _bad_names:
            # v12: tenta recuperar o nome real a partir da URL antes de descartar
            _name_from_url = None
            try:
                _nm = re.search(r'/maps/place/([^/@]+)', maps_canonical_url)
                if _nm:
                    _name_from_url = urllib.parse.unquote_plus(_nm.group(1)).replace('+', ' ').strip()
                    if _name_from_url and _name_from_url.lower() not in _bad_names and len(_name_from_url) > 3:
                        logger.info(f"[Maps][v12] Nome recuperado da URL: '{_name_from_url}' (era '{_raw_name}')")
                        _raw_name = _name_from_url
            except Exception:
                pass

            if _raw_name.lower() in _bad_names:
                logger.warning(
                    f"[Maps][v11] Nome inválido '{_raw_name}' (h1 capturado como aba) — descartando. "
                    f"URL: {maps_canonical_url[:80]}"
                )
                return None

        data = {
            'name':                  _raw_name,
            'category':              js_data.get('category') or '',
            'city':                  city,
            'phone_number':          phone_raw,
            'normalized_phone':      normalized,
            'website':               raw_website if website_type == 'website' else None,
            'website_detected_type': website_type,
            'instagram':             instagram,
            'facebook':              facebook,
            'youtube':               youtube,
            'twitter':               twitter or tiktok_val,  # tiktok como fallback
            'linkedin':              linkedin,
            'bio':                   (js_data.get('bio') or '')[:800],
            'address':               js_data.get('address'),
            'rating':                rating,
            'review_count':          review_count,
            'recent_reviews':        reviews_js if reviews_js else None,
            'business_hours':        hours_clean if hours_clean else None,
            'maps_url':              _clean_maps_url(maps_canonical_url),
            'maps_share_url':        share_final,
            'profile_picture_url':   profile_pic,
            'source':                'google_maps',
            'status':                'novo',
            'is_verified':           False,
            # ── Campos extras v10/v11 ──────────────────────────────────────
            '_price_range':          js_data.get('price_range'),
            '_plus_code':            js_data.get('plus_code'),
            '_amenities':            _am_merged,
            '_total_photos':         js_data.get('total_photos'),
            '_tiktok':               tiktok_val,
            # ── Campos novos v12 ───────────────────────────────────────────
            '_latitude':             js_data.get('latitude'),
            '_longitude':            js_data.get('longitude'),
            '_coordinates':          js_data.get('coordinates'),
            '_cid':                  js_data.get('cid') or _extract_cid_from_url(maps_canonical_url),
            '_kgmid':                js_data.get('kgmid'),
            '_order_online':         js_data.get('order_online'),
            '_menu':                 js_data.get('menu'),
            '_reservations':         js_data.get('reservations'),
            '_popular_times':        js_data.get('popular_times'),
        }

        # v12: se lat/lng não vieram do JS, tenta extrair da URL canônica
        if not data['_latitude']:
            _lat, _lng = _extract_lat_lng_from_url(maps_canonical_url)
            if _lat:
                data['_latitude'] = _lat
                data['_longitude'] = _lng
                data['_coordinates'] = {'lat': _lat, 'lng': _lng}

        if not data['name']:
            return None

        # Valida cidade
        if not _validate_city(data, city):
            logger.info(f"[Maps] Descartado (cidade errada): {data['name']}")
            return None

        logger.info(
            f"[Maps] OK: {data['name']} | tel={data.get('phone_number')} | "
            f"ig={data.get('instagram')} | rating={data.get('rating')} | "
            f"reviews={data.get('review_count')} | hours={bool(data.get('business_hours'))} | "
            f"maps_url={bool(data.get('maps_url'))}"
        )

        return data

    except Exception as e:
        logger.warning(f"[Maps] Erro ao extrair {url}: {e}")
        if page:
            try:
                await page.close()
            except Exception:
                pass
        return None


def _extract_place(context, url, city, **kwargs):
    raise RuntimeError("Use _extract_place_async")


# ---------------------------------------------------------------------------
# _parse_place_html — extração via BeautifulSoup
# ---------------------------------------------------------------------------

def _parse_place_html(
    html: str,
    maps_url: str,
    city: str,
    only_without_website: bool = False,
    min_rating: float | None = None,
    min_reviews: int | None = None,
    only_with_instagram: bool = False,
    only_with_facebook: bool = False,
    share_url: str | None = None,
    instagram_hint: str | None = None,
    linkedin_hint: str | None = None,
    facebook_hint: str | None = None,
    youtube_hint: str | None = None,
    twitter_hint: str | None = None,
    tiktok_hint: str | None = None,
    whatsapp_hint: str | None = None,
    place_photo_url: str | None = None,
    web_results_social: dict | None = None,
) -> dict | None:
    soup = BeautifulSoup(html, 'html.parser')
    full_text = soup.get_text(' ', strip=True)
    data = {}

    # ── Nome ──────────────────────────────────────────────────────────────────
    h1 = soup.find('h1')
    if not h1 or len(h1.get_text(strip=True)) < 2:
        return None
    data['name'] = h1.get_text(strip=True)

    # ── Categoria aprimorada ──────────────────────────────────────────────────
    # Tenta múltiplos seletores em ordem de confiança
    cat_candidates = (
        soup.select('button[jsaction*="category"]') or  # botão "Advogado trabalhista" na ficha
        soup.select('span[jsan*="category"]') or
        soup.select('div.fontBodyMedium button') or
        soup.select('button[jsaction] span, div[jsaction] span')
    )
    for el in cat_candidates:
        txt = el.get_text(strip=True)
        if 3 < len(txt) < 80 and not re.search(r'\d{4}', txt) and txt != data['name']:
            # Exclui textos que são claramente botões de ação
            skip_words = ('Rotas', 'Salvar', 'Compartilhar', 'Avaliar', 'Ligar', 'Enviar',
                          'Próximo', 'Sugerir', 'Fotos', 'Adicionar', 'Ordenar', 'Pesquisar',
                          'Smartphone', 'Avaliações', 'Sobre', 'Visão')
            if not any(sw.lower() in txt.lower() for sw in skip_words):
                data['category'] = txt
                break

    # ── Bio / Descrição do lugar ──────────────────────────────────────────────
    bio_text = None
    # 1) Seção "Sobre" / "Resumo"
    for el in soup.select('[aria-label*="Sobre"], [aria-label*="Resumo"], [data-item-id*="editorial"]'):
        t = el.get_text(' ', strip=True)
        if 20 < len(t) < 1000:
            bio_text = t
            break
    # 2) Parágrafo descritivo dentro do painel
    if not bio_text:
        for el in soup.select('div.PYvSYb, div.ZD2Oce, span.HlvSq'):
            t = el.get_text(strip=True)
            if 20 < len(t) < 600:
                bio_text = t
                break
    if bio_text:
        data['bio'] = bio_text[:800]

    # ── Telefone ──────────────────────────────────────────────────────────────
    phone_raw = None
    for el in soup.find_all(attrs={'aria-label': True}):
        label = el['aria-label']
        if 'telefone' in label.lower() or 'phone' in label.lower():
            m = re.search(r'[\d\s()\-+]{7,}', label)
            if m:
                phone_raw = m.group(0).strip()
                break

    if not phone_raw:
        matches = re.findall(
            r'\(?\d{2}\)?\s?(?:9\s?\d{4}|\d{4})[-\s]?\d{4}',
            full_text
        )
        expected_ddd = get_ddd(city)
        for m in matches:
            digits = re.sub(r'\D', '', m)
            if expected_ddd and digits.startswith(expected_ddd):
                phone_raw = m
                break
        if not phone_raw and matches:
            phone_raw = matches[0]

    if phone_raw:
        data['phone_number'] = phone_raw.strip()
        data['normalized_phone'] = normalize_phone(phone_raw)

    # ── Endereço ──────────────────────────────────────────────────────────────
    for el in soup.find_all(attrs={'aria-label': True}):
        label = el['aria-label']
        if 'endereço' in label.lower() or 'address' in label.lower():
            addr = label.replace('Endereço:', '').replace('Address:', '').strip()
            if len(addr) > 5:
                data['address'] = addr
                break

    if not data.get('address'):
        addr_match = re.search(
            r'((?:Rua|Av(?:enida)?\.?|Alameda|Travessa|Rod(?:ovia)?\.?|Estrada|Praça|Al\.)[^,\n]{3,60},'
            r'[^,\n]{1,50}(?:,\s*[^,\n]{2,40})?)',
            full_text, re.IGNORECASE
        )
        if addr_match:
            data['address'] = addr_match.group(1).strip()

    # ── Website ───────────────────────────────────────────────────────────────
    raw_website = None
    for a in soup.find_all('a', href=True):
        href = a['href']
        if (href.startswith('http') and
                'google' not in href and
                'maps' not in href and
                'goo.gl' not in href):
            parsed = urllib.parse.urlparse(href)
            if parsed.netloc:
                raw_website = href
                break

    data['website'] = raw_website
    data['website_detected_type'] = detect_website_type(raw_website)
    _resolve_social_from_website(raw_website, data)

    if only_without_website and data.get('website') and data.get('website_detected_type') == 'website':
        return None

    # ── Redes Sociais ─────────────────────────────────────────────────────────
    social = _extract_social_links(soup, full_text)
    for k, v in social.items():
        if v and not data.get(k):
            data[k] = v

    web_social = _extract_web_results_social(soup)
    for k, v in web_social.items():
        if v and not data.get(k):
            data[k] = v

    # v8: aplica dados do iframe "Resultados da Web" (mais confiável)
    if web_results_social:
        for k, v in web_results_social.items():
            if v and not data.get(k):
                data[k] = v

    if instagram_hint and not data.get('instagram'):
        handle = instagram_hint.lstrip('@')
        bad = ('explore', 'reel', 'reels', 'p', 'stories', 'tv', 'accounts', 'tags', 'share')
        if handle.lower() not in bad:
            data['instagram'] = instagram_hint

    # Aplica hints de LinkedIn, Facebook, YouTube, Twitter vindos do JS
    if linkedin_hint and not data.get('linkedin'):
        data['linkedin'] = linkedin_hint
    if facebook_hint and not data.get('facebook'):
        bad_fb = ('share', 'sharer', 'intent', 'home', 'watch', 'results', 'search', 'jobs', 'feed')
        handle = facebook_hint.rstrip('/').split('/')[-1]
        if handle.lower() not in bad_fb:
            data['facebook'] = facebook_hint
    if youtube_hint and not data.get('youtube'):
        data['youtube'] = youtube_hint
    if twitter_hint and not data.get('twitter'):
        bad_tw = ('share', 'intent', 'home', 'search', 'explore')
        handle = twitter_hint.rstrip('/').split('/')[-1]
        if handle.lower() not in bad_tw:
            data['twitter'] = twitter_hint
    if tiktok_hint and not data.get('tiktok'):
        data['tiktok'] = tiktok_hint  # salva em twitter se não tiver campo dedicado

    # v8: WhatsApp via link de agendamento — preenche phone se estiver vazio
    if whatsapp_hint:
        if not data.get('normalized_phone'):
            data['normalized_phone'] = whatsapp_hint if whatsapp_hint.startswith('55') else f"55{whatsapp_hint}"
        if not data.get('phone_number'):
            digits = whatsapp_hint
            if len(digits) >= 10:
                data['phone_number'] = f"({digits[-10:-8]}) {digits[-8:-4]}-{digits[-4:]}"

    # ── Avaliação ─────────────────────────────────────────────────────────────
    rating = None
    for el in soup.find_all(attrs={'aria-label': True}):
        label = el['aria-label']
        m = re.search(r'([1-5][.,]\d)\s*(?:estrelas?|stars?)', label, re.IGNORECASE)
        if m:
            try:
                rating = float(m.group(1).replace(',', '.'))
                break
            except ValueError:
                pass

    if not rating:
        for el in soup.select('span.ceNzKf, span[aria-label*="estrela"], div.fontDisplayLarge'):
            txt = el.get_text(strip=True).replace(',', '.')
            m = re.match(r'^([1-5]\.\d)$', txt)
            if m:
                try:
                    rating = float(m.group(1))
                    break
                except ValueError:
                    pass

    if not rating:
        for m in re.finditer(r'\b([1-5][.,]\d)\b', full_text):
            context_slice = full_text[max(0, m.start()-40):m.end()+40]
            if re.search(r'estrela|avalia|rating|star', context_slice, re.IGNORECASE):
                try:
                    rating = float(m.group(1).replace(',', '.'))
                    break
                except ValueError:
                    pass

    if rating:
        data['rating'] = rating

    if min_rating is not None and (not data.get('rating') or data['rating'] < min_rating):
        return None

    # ── Review count ──────────────────────────────────────────────────────────
    review_count = 0

    # 1) Seletor mais confiável: botão "X avaliações" na seção de resumo (ex: "17 avaliações")
    for el in soup.select('button.GQjSyb, button[jsaction*="moreReviews"]'):
        m = re.search(r'([\d.,]+)\s*avalia', el.get_text(strip=True), re.IGNORECASE)
        if m:
            try:
                review_count = int(re.sub(r'\D', '', m.group(1)))
                if review_count > 0:
                    break
            except ValueError:
                pass

    # 2) aria-label "X avaliações" em qualquer elemento
    if not review_count:
        for el in soup.find_all(attrs={'aria-label': True}):
            label = el['aria-label']
            rm = re.search(r'([\d.,]+)\s*(?:avaliações|avaliação|reviews?|comentários)', label, re.IGNORECASE)
            if rm:
                try:
                    review_count = int(re.sub(r'\D', '', rm.group(1)))
                    if review_count > 0:
                        break
                except ValueError:
                    pass

    # 3) Texto livre: "17 avaliações" ou "(17)"
    if not review_count:
        review_patterns = [
            r'([\d][.\d]*[\d]|[\d]+)\s*(?:avaliações|avaliação|reviews?|comentários)',
            r'\((\d[\d.,]*\d|\d+)\)',
        ]
        for pat in review_patterns:
            rm = re.search(pat, full_text, re.IGNORECASE)
            if rm:
                try:
                    review_count = int(re.sub(r'\D', '', rm.group(1)))
                    if review_count > 0:
                        break
                except ValueError:
                    pass

    data['review_count'] = review_count

    if min_reviews is not None and data['review_count'] < min_reviews:
        return None

    data['recent_reviews'] = _extract_recent_reviews(soup)
    data['business_hours'] = _extract_business_hours(soup, full_text)
    data['maps_url'] = _clean_maps_url(maps_url) if maps_url else None
    data['maps_share_url'] = share_url or _extract_share_url(soup, full_text)
    data['city'] = city

    if not _validate_city(data, city):
        logger.info(f"[Maps] Descartado (cidade errada): {data['name']} — {data.get('address', '')}")
        return None

    if only_with_instagram and not data.get('instagram'):
        return None
    if only_with_facebook and not data.get('facebook'):
        return None

    if data.get('instagram'):
        pic = fetch_instagram_profile_pic(data['instagram'])
        if pic:
            data['profile_picture_url'] = pic

    # v8: se não conseguiu foto do Instagram, usa a foto principal da ficha do Maps
    if not data.get('profile_picture_url') and place_photo_url:
        data['profile_picture_url'] = place_photo_url

    data.setdefault('bio', '')
    data.setdefault('facebook', None)
    data.setdefault('youtube', None)
    data.setdefault('twitter', None)
    data.setdefault('instagram', None)
    data.setdefault('linkedin', None)
    data.setdefault('profile_picture_url', None)
    data['source'] = 'google_maps'
    data['status'] = 'novo'
    data['is_verified'] = False

    return data


# ---------------------------------------------------------------------------
# _extract_social_links
# ---------------------------------------------------------------------------

def _extract_social_links(soup: BeautifulSoup, full_text: str) -> dict:
    social = {
        'instagram': None,
        'facebook': None,
        'youtube': None,
        'twitter': None,
        'linkedin': None,
    }

    social_patterns = {
        'instagram': re.compile(r'instagram\.com/([A-Za-z0-9._]{1,50})/?'),
        'facebook':  re.compile(r'facebook\.com/([A-Za-z0-9._\-]{1,80})/?'),
        'youtube':   re.compile(r'youtube\.com/(?:channel/|c/|@)([A-Za-z0-9._\-]{1,80})/?'),
        'twitter':   re.compile(r'(?:twitter|x)\.com/([A-Za-z0-9._]{1,50})/?'),
        'linkedin':  re.compile(r'linkedin\.com/(?:company|in)/([A-Za-z0-9._\-]{1,80})/?'),
    }

    for a in soup.find_all('a', href=True):
        href = a['href']
        for network, pattern in social_patterns.items():
            if social[network]:
                continue
            m = pattern.search(href)
            if m:
                handle = m.group(1).rstrip('/')
                if handle.lower() in ('share', 'sharer', 'intent', 'home', 'watch',
                                       'results', 'search', 'jobs', 'feed', 'notifications'):
                    continue
                if network == 'instagram':
                    social[network] = f"@{handle}"
                else:
                    full = re.sub(r'[?#].*', '', href)
                    social[network] = full

    for network, pattern in social_patterns.items():
        if social[network]:
            continue
        m = pattern.search(full_text)
        if m:
            handle = m.group(1)
            if handle.lower() in ('share', 'sharer', 'intent', 'home', 'watch',
                                   'results', 'jobs', 'feed'):
                continue
            if network == 'instagram':
                social[network] = f"@{handle}"
            elif network == 'linkedin':
                social[network] = f"https://linkedin.com/company/{handle}"
            else:
                social[network] = f"https://{network}.com/{handle}"

    return social


# ---------------------------------------------------------------------------
# _extract_business_hours
# ---------------------------------------------------------------------------

def _extract_business_hours(soup: BeautifulSoup, full_text: str) -> dict | None:
    hours: dict = {}

    _DAY_DISPLAY = {
        'segunda': 'segunda-feira',
        'segunda-feira': 'segunda-feira',
        'terça': 'terça-feira',
        'terca': 'terça-feira',
        'terça-feira': 'terça-feira',
        'terca-feira': 'terça-feira',
        'quarta': 'quarta-feira',
        'quarta-feira': 'quarta-feira',
        'quinta': 'quinta-feira',
        'quinta-feira': 'quinta-feira',
        'sexta': 'sexta-feira',
        'sexta-feira': 'sexta-feira',
        'sábado': 'sábado',
        'sabado': 'sábado',
        'domingo': 'domingo',
    }

    def _parse_time_range(text: str) -> str | None:
        m = re.search(r'(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})', text)
        if m:
            return f"{m.group(1)}–{m.group(2)}"
        if re.search(r'fechado|closed', text, re.IGNORECASE):
            return 'Fechado'
        if re.search(r'aberto\s*24\s*horas|open\s*24', text, re.IGNORECASE):
            return '00:00–23:59'
        return None

    # ── Estratégia 1: aria-label de elementos com múltiplos dias ────────────
    for el in soup.find_all(attrs={'aria-label': True}):
        label = el['aria-label']
        matches_days = re.findall(
            r'(segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo)[\s\-feira]*\s*:?\s*'
            r'([\d:–\-\s]+|fechado|aberto\s*24\s*horas)',
            label, re.IGNORECASE
        )
        if len(matches_days) >= 2:
            for raw_day, raw_hours in matches_days:
                display_day = _DAY_DISPLAY.get(raw_day.lower().strip())
                if not display_day:
                    continue
                parsed = _parse_time_range(raw_hours)
                if parsed and display_day not in hours:
                    hours[display_day] = parsed
            if hours:
                break

    # ── Estratégia 2: tabela de horários (várias classes possíveis) ──────────
    # Estrutura real do Maps: tr.y0skZc com td.ylH6lf (dia) + td.mxowUb (horário)
    if not hours:
        table_rows = (
            soup.select('tr.y0skZc') or             # seletor mais preciso do Maps real
            soup.select('table.eK4R0e tr') or
            soup.select('table.WgFkxc tr') or
            soup.select('[jsaction*="openhours"] tr') or
            soup.select('div[aria-label*="Horário"] tr') or
            soup.select('div[class*="t39EBf"] tr') or
            []
        )
        for row in table_rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                day_text = cells[0].get_text(' ', strip=True).lower().strip()
                hour_text = cells[1].get_text(' ', strip=True)
                # Tenta mapeamento direto E variações sem "-feira"
                display_day = _DAY_DISPLAY.get(day_text)
                if not display_day:
                    # Tenta sem "-feira" (ex: "segunda" ao invés de "segunda-feira")
                    short = day_text.split('-')[0].split(' ')[0]
                    display_day = _DAY_DISPLAY.get(short)
                if display_day and display_day not in hours:
                    parsed = _parse_time_range(hour_text)
                    if parsed:
                        hours[display_day] = parsed
                    elif re.search(r'atendimento\s*24\s*horas', hour_text, re.IGNORECASE):
                        hours[display_day] = '00:00–23:59'
                    elif hour_text.strip():
                        # Captura texto como está se não reconheceu o padrão
                        hours[display_day] = hour_text.strip()[:30]

    # ── Estratégia 3: aria-label individuais por dia ("segunda-feira, 08:00 a 18:00") ──
    if not hours:
        for el in soup.find_all(attrs={'aria-label': True}):
            label = el['aria-label']
            # Formato: "segunda-feira, 08:00 a 18:00" ou "domingo, Fechado"
            m_single = re.match(
                r'(segunda[\-\s]feira|terça[\-\s]feira|quarta[\-\s]feira|quinta[\-\s]feira|'
                r'sexta[\-\s]feira|sábado|sabado|domingo)\s*,\s*(.+)',
                label, re.IGNORECASE
            )
            if m_single:
                raw_day = m_single.group(1).lower().replace(' ', '-')
                raw_hours_str = m_single.group(2)
                display_day = _DAY_DISPLAY.get(raw_day) or _DAY_DISPLAY.get(raw_day.split('-')[0])
                if display_day and display_day not in hours:
                    parsed = _parse_time_range(raw_hours_str)
                    if not parsed and re.search(r'fechado', raw_hours_str, re.IGNORECASE):
                        parsed = 'Fechado'
                    if parsed:
                        hours[display_day] = parsed

    if not hours:
        for raw_day, display_day in _DAY_DISPLAY.items():
            if display_day in hours:
                continue
            pattern = re.compile(
                rf'\b{re.escape(raw_day)}\b[^\n]{{0,30}}'
                rf'(\d{{1,2}}:\d{{2}}\s*[–\-]\s*\d{{1,2}}:\d{{2}}|fechado|aberto\s*24\s*horas)',
                re.IGNORECASE
            )
            m = pattern.search(full_text)
            if m:
                parsed = _parse_time_range(m.group(0))
                if parsed:
                    hours[display_day] = parsed

    status_m = re.search(
        r'(Aberto\s*(?:24\s*horas)?|Fechado\s*(?:agora)?|Abre\s*às\s*\d{1,2}:\d{2}|Fecha\s*às\s*\d{1,2}:\d{2})',
        full_text, re.IGNORECASE
    )
    if status_m:
        hours['status_atual'] = status_m.group(1).strip()

    if re.search(r'\baberto\b', full_text, re.IGNORECASE):
        hours['aberto_agora'] = True
    elif re.search(r'\bfechado\b', full_text, re.IGNORECASE):
        hours['aberto_agora'] = False

    return hours if hours else None


# ---------------------------------------------------------------------------
# _extract_web_results_social
# ---------------------------------------------------------------------------

def _extract_web_results_social(soup: BeautifulSoup) -> dict:
    found = {}

    web_section_patterns = [
        soup.select('div[jsaction*="web_result"]'),
        soup.select('a[data-value*="web"]'),
        [a for a in soup.find_all('a', href=True)
         if 'google' not in a.get('href', '') and
            'goo.gl' not in a.get('href', '') and
            a.get('href', '').startswith('http')],
    ]

    social_patterns = {
        'instagram': re.compile(r'instagram\.com/([A-Za-z0-9._]{2,50})/?'),
        'linkedin':  re.compile(r'linkedin\.com/(?:company|in)/([A-Za-z0-9._\-]{2,80})/?'),
        'facebook':  re.compile(r'facebook\.com/([A-Za-z0-9._\-]{2,80})/?'),
    }

    for elements in web_section_patterns:
        for el in elements:
            href = el.get('href', '') if hasattr(el, 'get') else ''
            text = el.get_text(' ', strip=True) if hasattr(el, 'get_text') else ''
            combined = href + ' ' + text
            for network, pattern in social_patterns.items():
                if found.get(network):
                    continue
                m = pattern.search(combined)
                if m:
                    handle = m.group(1).rstrip('/')
                    bad = ('share', 'sharer', 'intent', 'home', 'watch',
                           'results', 'search', 'jobs', 'feed', 'explore',
                           'reels', 'stories', 'p', 'reel')
                    if handle.lower() in bad:
                        continue
                    if network == 'instagram':
                        found[network] = f"@{handle}"
                    elif network == 'linkedin':
                        found[network] = f"https://linkedin.com/company/{handle}"
                    else:
                        found[network] = re.sub(r'[?#].*', '', href) or f"https://facebook.com/{handle}"

    return found


# ---------------------------------------------------------------------------
# v8: _extract_web_results_full — lê HTML do iframe "Resultados da Web"
# ---------------------------------------------------------------------------

def _extract_web_results_full(iframe_html: str) -> dict:
    """
    Analisa o HTML do iframe /search?pcl=lp para extrair redes sociais.
    O iframe mostra links reais do site, Instagram, Facebook, LinkedIn, etc.
    """
    found: dict = {}
    if not iframe_html:
        return found

    soup_w = BeautifulSoup(iframe_html, 'html.parser')

    # Padrões expandidos — inclui YouTube, TikTok, Twitter/X
    patterns = {
        'instagram': re.compile(r'instagram\.com/([A-Za-z0-9._]{2,50})/?'),
        'linkedin':  re.compile(r'linkedin\.com/(?:company|in)/([A-Za-z0-9._\-]{2,80})/?'),
        'facebook':  re.compile(r'facebook\.com/([A-Za-z0-9._\-]{2,80})/?'),
        'youtube':   re.compile(r'youtube\.com/(?:channel/|c/|@)([A-Za-z0-9._\-]{2,80})/?'),
        'twitter':   re.compile(r'(?:twitter|x)\.com/([A-Za-z0-9._]{2,50})/?'),
        'tiktok':    re.compile(r'tiktok\.com/@([A-Za-z0-9._]{2,50})/?'),
    }
    bad_handles = {
        'share', 'sharer', 'intent', 'home', 'watch', 'results', 'search',
        'jobs', 'feed', 'explore', 'reels', 'stories', 'p', 'reel', 'ads',
        'about', 'legal', 'privacy', 'support', 'notifications',
    }

    # 1) Links diretos no iframe
    for a in soup_w.find_all('a', href=True):
        href = a['href']
        for network, pattern in patterns.items():
            if found.get(network):
                continue
            m = pattern.search(href)
            if m:
                handle = m.group(1).rstrip('/')
                if handle.lower() in bad_handles:
                    continue
                if network == 'instagram':
                    found[network] = f"@{handle}"
                elif network == 'tiktok':
                    found[network] = f"@{handle}"
                elif network in ('linkedin', 'facebook', 'youtube', 'twitter'):
                    clean = re.sub(r'[?#].*', '', href)
                    found[network] = clean

    # 2) Texto visível (URLs escritas em texto) — captura "instagram.com/handle"
    full_text_w = soup_w.get_text(' ', strip=True)
    for network, pattern in patterns.items():
        if found.get(network):
            continue
        m = pattern.search(full_text_w)
        if m:
            handle = m.group(1).rstrip('/')
            if handle.lower() not in bad_handles:
                if network == 'instagram':
                    found[network] = f"@{handle}"
                elif network == 'linkedin':
                    found[network] = f"https://linkedin.com/company/{handle}"
                elif network == 'facebook':
                    found[network] = f"https://facebook.com/{handle}"
                elif network == 'youtube':
                    found[network] = f"https://youtube.com/@{handle}"
                elif network == 'twitter':
                    found[network] = f"https://x.com/{handle}"

    # 3) Snippets visíveis com handles @usuario
    if not found.get('instagram'):
        m = re.search(r'@([A-Za-z0-9._]{2,50})\b', full_text_w)
        if m and 'instagram' in full_text_w.lower():
            found['instagram'] = f"@{m.group(1)}"

    return found

def _extract_recent_reviews(soup: BeautifulSoup) -> list | None:
    """
    v8.1: Extrai até 10 avaliações com:
    - autor + badge (Local Guide, qtd reviews, fotos)
    - nota (1-5 estrelas)
    - data relativa ("3 meses atrás")
    - texto completo (já expandido pelo Playwright antes de capturar o HTML)
    - resposta do proprietário (texto + data)

    Corrigido v8.1:
    - Deduplicação por (autor, data, texto) para evitar reviews repetidos
    - Preferência por [data-review-id] (seletor mais preciso); só usa fallback
      jsaction*="review" se o primeiro não retornar nada
    - Filtra containers sem nenhum dado útil
    """
    reviews = []
    seen: set[str] = set()  # chave de dedup: (author|date|text)

    # Seletor 1 — containers com id único de review (mais confiável)
    review_containers = soup.select('[data-review-id]')

    # Seletor 2 — fallback: div com jsaction de review que não seja filho de [data-review-id]
    if not review_containers:
        all_jsaction = soup.select('div[jsaction*="review"]')
        review_containers = [
            el for el in all_jsaction
            if not el.find_parent(attrs={'data-review-id': True})
        ]

    # Seletor 3 — fallback adicional: classe jftiEf (container de review)
    if not review_containers:
        review_containers = soup.select('div.jftiEf')

    for container in review_containers[:25]:  # processa mais, deduplica depois
        review: dict = {}

        # Autor
        for sel in ('div[class*="d4r55"]', 'div.d4r55', 'button.al6Kxe div.d4r55', '.WNxzHc .d4r55'):
            author_el = container.select_one(sel)
            if author_el:
                t = author_el.get_text(strip=True)
                if t:
                    review['author'] = t
                    break

        # Badge do avaliador
        for sel in ('div[class*="RfnDt"]', 'div.RfnDt', '.GHT2ce .RfnDt'):
            badge_el = container.select_one(sel)
            if badge_el:
                t = badge_el.get_text(strip=True)
                if t:
                    review['author_badge'] = t
                    break

        # Nota em estrelas
        rating_el = container.find(attrs={'aria-label': re.compile(r'(\d)\s*estrela', re.I)})
        if rating_el:
            rm = re.search(r'(\d)', rating_el['aria-label'])
            if rm:
                review['rating'] = int(rm.group(1))

        # Data relativa
        for sel in ('span[class*="rsqaWe"]', 'span.rsqaWe', 'span[class*="xRkPPb"]'):
            date_el = container.select_one(sel)
            if date_el:
                t = date_el.get_text(strip=True)
                if t:
                    review['date'] = t
                    break

        # Texto da avaliação — tenta múltiplos seletores
        for sel in ('span[class*="wiI7pd"]', 'span.wiI7pd', 'div[class*="review-full-text"]',
                    '[class*="MyEned"] span', 'div.MyEned span'):
            text_el = container.select_one(sel)
            if text_el:
                t = text_el.get_text(strip=True)
                if t and len(t) > 3:
                    review['text'] = t[:1000]
                    break

        # Resposta do proprietário
        owner_reply_el = container.select_one('div[class*="CDe7pd"], div.CDe7pd')
        if owner_reply_el:
            owner_date_el = owner_reply_el.select_one('span[class*="DZSIDd"], span.DZSIDd')
            owner_date = owner_date_el.get_text(strip=True) if owner_date_el else None
            owner_text_el = owner_reply_el.select_one('span[class*="wiI7pd"], div.wiI7pd')
            owner_text = owner_text_el.get_text(strip=True) if owner_text_el else None
            if owner_text:
                review['owner_reply'] = owner_text[:500]
                if owner_date:
                    review['owner_reply_date'] = owner_date
            if owner_date:
                review['owner_reply_date'] = owner_date

        # Descarta containers sem dados úteis
        if not (review.get('author') or review.get('text') or review.get('rating')):
            continue

        # Deduplicação: chave composta de autor + data + primeiros 60 chars do texto
        dedup_key = '|'.join([
            (review.get('author') or '').lower().strip(),
            (review.get('date') or '').lower().strip(),
            (review.get('text') or '')[:60].lower().strip(),
        ])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        reviews.append(review)
        if len(reviews) >= 10:
            break

    # Fallback: aria-label (quando a página não renderizou os containers)
    if not reviews:
        for el in soup.find_all(attrs={'aria-label': True}):
            label = el['aria-label']
            m = re.search(
                r'(\d)\s*estrela[s]?[^,\n]{0,40}[,\s]+(há\s+\d+[^\n,]{0,20})',
                label, re.IGNORECASE
            )
            if m:
                dedup_key = label[:80].lower()
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                reviews.append({
                    'rating': int(m.group(1)),
                    'date': m.group(2).strip(),
                    'text': label[:300],
                })
                if len(reviews) >= 10:
                    break

    return reviews if reviews else None


# ---------------------------------------------------------------------------
# _extract_share_url
# ---------------------------------------------------------------------------

def _extract_share_url(soup: BeautifulSoup, full_text: str) -> str | None:
    patterns = [
        re.compile(r'https://share\.google/[A-Za-z0-9_\-]{6,}'),
        re.compile(r'https://maps\.app\.goo\.gl/[A-Za-z0-9_\-]{6,}'),
        re.compile(r'https://goo\.gl/maps/[A-Za-z0-9_\-]{6,}'),
    ]
    for pattern in patterns:
        m = pattern.search(full_text)
        if m:
            return m.group(0)
    return None


# ---------------------------------------------------------------------------
# _clean_maps_url
# ---------------------------------------------------------------------------

def _clean_maps_url(url: str) -> str:
    if not url:
        return url
    try:
        parsed = urllib.parse.urlparse(url)
        params_to_keep = {}
        qs = urllib.parse.parse_qs(parsed.query)
        for k, v in qs.items():
            if k not in ('hl', 'ved', 'ei', 'sa', 'source'):
                params_to_keep[k] = v
        new_query = urllib.parse.urlencode(params_to_keep, doseq=True)
        clean = urllib.parse.urlunparse((
            parsed.scheme, parsed.netloc, parsed.path, '', new_query, ''
        ))
        return clean
    except Exception:
        return url


# ---------------------------------------------------------------------------
# _validate_city
# ---------------------------------------------------------------------------

def _validate_city(data: dict, requested_city: str) -> bool:
    city_lower = requested_city.lower().strip()
    tokens = [t for t in city_lower.split() if len(t) > 2]

    address = (data.get('address') or '').lower()
    phone_digits = re.sub(r'\D', '', data.get('phone_number') or '')
    expected_ddd = get_ddd(requested_city)

    has_address = bool(address)
    has_phone   = bool(phone_digits)

    if has_address and any(t in address for t in tokens):
        return True
    if has_phone and expected_ddd:
        if phone_digits.startswith(expected_ddd) or phone_digits.startswith('55' + expected_ddd):
            return True
    if not has_address and not has_phone:
        return True
    return False


# ---------------------------------------------------------------------------
# Foto de perfil do Instagram
# ---------------------------------------------------------------------------

def fetch_instagram_profile_pic(instagram_handle: str) -> str | None:
    handle = instagram_handle.lstrip('@')
    url = f"https://www.instagram.com/{handle}/"
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept-Language': 'pt-BR,pt;q=0.9',
    }
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, 'html.parser')
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            return og['content']
        m = re.search(r'"profile_pic_url_hd"\s*:\s*"([^"]+)"', resp.text)
        if m:
            return m.group(1).replace('\\u0026', '&')
    except Exception as e:
        logger.debug(f"[Instagram] Falha ao buscar foto de {handle}: {e}")
    return None


# ---------------------------------------------------------------------------
# Pipeline principal — Google Maps
# ---------------------------------------------------------------------------

def _check_playwright_environment() -> str | None:
    """Verifica se o ambiente Playwright está pronto. Retorna None se OK."""
    try:
        from playwright.async_api import async_playwright  # noqa
    except ImportError:
        return "Playwright não instalado. Execute: pip install playwright && playwright install firefox"
    except Exception as e:
        return f"Falha ao importar playwright.async_api: {e}"
    return None


def run_google_maps_scraper(
    user,
    city: str,
    niche: str,
    limit: int,
    only_without_website: bool = False,
    min_rating: float | None = None,
    min_reviews: int | None = None,
    only_with_instagram: bool = False,
    only_with_facebook: bool = False,
    seed=None,
    # v12: novos parâmetros
    grid_bbox: str | None = None,
    grid_cell_km: float = 1.0,
    fast_mode: bool = False,
) -> tuple[int, int]:
    """
    Pipeline completo de scraping do Google Maps.

    v12 — novos parâmetros:
      grid_bbox (str | None): "minLat,minLon,maxLat,maxLon" para varredura em grade.
          Exemplo para Ribeirão Preto centro: "-21.25,-47.85,-21.15,-47.75"
          Use https://geojson.io para encontrar as coordenadas da sua área.
      grid_cell_km (float): tamanho das células da grade em km (padrão 1.0).
          0.5 = bloco nível rua (muito detalhado, lento)
          1.0 = sub-bairro (bom equilíbrio)
          2.0 = bairro (rápido, pode perder negócios em áreas densas)
      fast_mode (bool): coleta rápida sem abrir cada ficha.
          Retorna: nome, categoria, lat/lng, maps_url. Sem telefone/Instagram/reviews.

    ROLLBACK STAGES nos logs Django:
      [PIPELINE A] Verificação do Playwright
      [PIPELINE B] Chamada do scraper (subprocesso)
      [PIPELINE C] Salvamento dos leads no banco
    """
    import traceback as _tb

    # ── PIPELINE A: Verifica Playwright ──────────────────────────────────────
    logger.info(f"[Maps][PIPELINE A] ══ run_google_maps_scraper v12 iniciado ══")
    logger.info(f"[Maps][PIPELINE A] user={getattr(user, 'username', user)} niche={niche!r} city={city!r} limit={limit}")
    logger.info(f"[Maps][PIPELINE A] grid_bbox={grid_bbox!r} grid_cell_km={grid_cell_km} fast_mode={fast_mode}")

    env_problem = _check_playwright_environment()
    if env_problem:
        logger.error(f"[Maps][PIPELINE A] ✗ AMBIENTE INVÁLIDO: {env_problem}")
        raise RuntimeError(f"Playwright não configurado: {env_problem}")
    logger.info(f"[Maps][PIPELINE A] ✓ Playwright disponível")

    # ── PIPELINE B: Scraping ──────────────────────────────────────────────────
    logger.info(f"[Maps][PIPELINE B] ══ Chamando scrape_google_maps (subprocesso) ══")

    # v12: aviso proativo sobre combinações de filtros que costumam retornar zero
    if only_without_website and not min_reviews:
        logger.warning(
            "[Maps][PIPELINE B] ⚠️  AVISO: only_without_website=True sem min_reviews. "
            "A maioria dos negócios no Maps tem site. Considere usar min_reviews≥10 "
            "para reduzir o pool e aumentar a chance de encontrar sem site, "
            "ou desative o filtro para obter mais resultados."
        )
    if only_with_instagram and only_with_facebook:
        logger.warning(
            "[Maps][PIPELINE B] ⚠️  AVISO: only_with_instagram=True E only_with_facebook=True "
            "ao mesmo tempo é muito restritivo — poucos negócios têm ambos no Maps."
        )
    try:
        leads_data = scrape_google_maps(
            niche, city, limit,
            only_without_website=only_without_website,
            min_rating=min_rating,
            min_reviews=min_reviews,
            only_with_instagram=only_with_instagram,
            only_with_facebook=only_with_facebook,
            grid_bbox=grid_bbox,
            grid_cell_km=grid_cell_km,
            fast_mode=fast_mode,
        )
    except Exception as e:
        logger.error(f"[Maps][PIPELINE B] ✗ scrape_google_maps lançou exceção: {e}")
        logger.error(_tb.format_exc())
        raise

    logger.info(f"[Maps][PIPELINE B] ✓ scrape_google_maps retornou {len(leads_data)} leads")

    if len(leads_data) == 0:
        logger.warning(f"[Maps][PIPELINE B] ⚠️  ZERO leads para '{niche}' em '{city}'")
        logger.warning(f"[Maps][PIPELINE B]   → Veja os logs [Maps][STEP *] e [Maps:worker] acima")
        logger.warning(f"[Maps][PIPELINE B]   → Screenshots de diagnóstico em pasta tmp/ do projeto")

    # ── PIPELINE C: Salvamento ─────────────────────────────────────────────────
    logger.info(f"[Maps][PIPELINE C] ══ Salvando leads no banco ══")
    try:
        saved, skipped = _save_leads(user, leads_data[:limit])
        logger.info(f"[Maps][PIPELINE C] ✓ Salvos: {saved} | Duplicados ignorados: {skipped}")
        return saved, skipped
    except Exception as e:
        logger.error(f"[Maps][PIPELINE C] ✗ Erro ao salvar leads: {e}")
        logger.error(_tb.format_exc())
        raise


# ---------------------------------------------------------------------------
# Pipeline — Instagram
# ---------------------------------------------------------------------------

def run_instagram_scraper(user, niche: str, location: str | None = None,
                           limit: int = 10, only_verified: bool = False,
                           only_with_bio_link: bool = False, seed=None) -> tuple[int, int]:
    """Busca perfis reais do Instagram via DuckDuckGo dorks."""
    city = location or 'Brasil'
    leads_data: list[dict] = []
    seen_handles: set[str] = set()

    queries = [f'site:instagram.com "{niche}"']
    if location:
        queries = [
            f'site:instagram.com "{niche}" "{location}"',
            f'site:instagram.com "{niche}" {location}',
        ]

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
    }

    for query in queries:
        if len(leads_data) >= limit:
            break
        try:
            resp = requests.post(
                'https://html.duckduckgo.com/html/',
                headers=headers,
                data={'q': query},
                timeout=10,
            )
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            for result in soup.select('.result'):
                title_el   = result.select_one('.result__title a')
                snippet_el = result.select_one('.result__snippet')
                if not title_el:
                    continue
                href = title_el.get('href', '')
                parsed = urllib.parse.urlparse(href)
                if parsed.path == '/l/':
                    qs = urllib.parse.parse_qs(parsed.query)
                    href = qs.get('uddg', [href])[0]
                results.append({
                    'url':     href,
                    'snippet': snippet_el.get_text(strip=True) if snippet_el else '',
                })
        except Exception as e:
            logger.warning(f"[Instagram DDG] Erro: {e}")
            results = []

        time.sleep(random.uniform(1.5, 3.0))

        for r in results:
            if len(leads_data) >= limit:
                break
            url = r['url']
            if 'instagram.com' not in url:
                continue
            parts = [p for p in urllib.parse.urlparse(url).path.split('/') if p]
            if not parts:
                continue
            handle = parts[0]
            if handle in ('explore', 'reel', 'reels', 'p', 'stories', 'tv', 'accounts', 'tags'):
                continue
            if handle in seen_handles:
                continue
            seen_handles.add(handle)

            snippet = r['snippet']
            name    = handle.replace('.', ' ').replace('_', ' ').title()

            phone_m    = re.search(r'\(?\d{2}\)?\s?(?:9\s?\d{4}|\d{4})[-\s]?\d{4}', snippet)
            phone_raw  = phone_m.group(0) if phone_m else None
            norm_phone = normalize_phone(phone_raw) if phone_raw else None

            site_m  = re.search(r'https?://(?!(?:www\.)?instagram)[^\s"\'<>]{4,80}', snippet)
            website_raw = site_m.group(0).rstrip('.,)') if site_m else None

            website_type = detect_website_type(website_raw)
            website = website_raw if website_type == 'website' else None

            if only_with_bio_link and not website_raw:
                continue

            ddd = get_ddd(city) or '11'
            if not phone_raw:
                phone_raw = None
                norm_phone = None

            pic_url = fetch_instagram_profile_pic(handle)

            leads_data.append({
                'name':                  name,
                'category':              niche.title(),
                'city':                  city,
                'phone_number':          phone_raw,
                'normalized_phone':      norm_phone,
                'website':               website,
                'website_detected_type': website_type,
                'instagram':             f"@{handle}",
                'facebook':              None,
                'youtube':               None,
                'twitter':               None,
                'linkedin':              None,
                'bio':                   snippet[:250],
                'address':               None,
                'rating':                None,
                'review_count':          0,
                'recent_reviews':        None,
                'business_hours':        None,
                'maps_url':              None,
                'maps_share_url':        None,
                'profile_picture_url':   pic_url,
                'source':                'instagram',
                'status':                'novo',
                'is_verified':           only_verified,
            })

    if len(leads_data) == 0:
        logger.warning(f"[Instagram] Nenhum perfil encontrado para '{niche}' em '{city}'.")

    return _save_leads(user, leads_data[:limit])


# ---------------------------------------------------------------------------
# Deduplicação e salvamento
# ---------------------------------------------------------------------------

def _save_leads(user, leads: list[dict]) -> tuple[int, int]:
    saved = skipped = 0

    for item in leads:
        norm_p = item.get('normalized_phone')
        inst   = item.get('instagram')
        name   = item.get('name', '').strip()

        if not name:
            skipped += 1
            continue

        dup = (
            (norm_p and Lead.objects.filter(user=user, normalized_phone=norm_p).exists()) or
            Lead.objects.filter(user=user, name__iexact=name).exists() or
            (inst and Lead.objects.filter(user=user, instagram__iexact=inst).exists())
        )
        if dup:
            skipped += 1
            continue

        Lead.objects.create(
            user=user,
            name=name,
            category=item.get('category') or '',
            city=item.get('city') or '',
            phone_number=item.get('phone_number'),
            normalized_phone=norm_p,
            website=item.get('website'),
            website_detected_type=item.get('website_detected_type'),
            instagram=inst,
            facebook=item.get('facebook'),
            youtube=item.get('youtube'),
            twitter=item.get('twitter'),
            linkedin=item.get('linkedin'),
            bio=item.get('bio') or '',
            address=item.get('address'),
            rating=item.get('rating'),
            review_count=item.get('review_count') or 0,
            recent_reviews=item.get('recent_reviews'),
            business_hours=item.get('business_hours'),
            maps_url=item.get('maps_url'),
            maps_share_url=item.get('maps_share_url'),
            profile_picture_url=item.get('profile_picture_url'),
            source=item.get('source', 'google_maps'),
            status='novo',
            is_verified=item.get('is_verified', False),
            # v10: campos extras do Maps
            price_range=item.get('_price_range'),
            plus_code=item.get('_plus_code'),
            amenities=item.get('_amenities') or None,
            total_photos=item.get('_total_photos'),
        )
        saved += 1

    return saved, skipped