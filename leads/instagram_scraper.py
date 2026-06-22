"""Scraper Instagram via DuckDuckGo — sem Playwright."""

import logging
import random
import re
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

from .import_utils import save_leads_from_dicts
from .website_utils import detect_website_type

logger = logging.getLogger(__name__)

CITY_DDDS = {
    'ribeirão preto': '16', 'ribeirao preto': '16',
    'são paulo': '11', 'sao paulo': '11', 'sp': '11',
    'campinas': '19', 'curitiba': '41', 'belo horizonte': '31',
}

USER_AGENTS = [
    ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
     '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'),
    ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
     '(KHTML, like Gecko) Version/17.4 Safari/605.1.15'),
    ('Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0'),
]

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

SKIP_HANDLES = {
    'explore', 'reel', 'reels', 'p', 'stories', 'tv', 'accounts', 'tags',
    'directory', 'about', 'developer', 'legal', 'privacy', 'web',
}


def _headers() -> dict:
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }


def _clean_unicode(value: str) -> str:
    return (value or '').replace('\\u0026', '&').replace('&amp;', '&').replace('\\/', '/')


def normalize_phone(phone: str) -> str | None:
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


def fetch_instagram_profile_pic(handle: str) -> str | None:
    handle = handle.lstrip('@')
    url = f'https://www.instagram.com/{handle}/'
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept-Language': 'pt-BR,pt;q=0.9',
    }
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return None
        text = resp.text
        soup = BeautifulSoup(text, 'html.parser')
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            og_url = og['content'].replace('\\u0026', '&').replace('&amp;', '&')
            if '/static/' not in og_url:
                return og_url
        m = re.search(r'"profile_pic_url_hd"\s*:\s*"([^"]+)"', text)
        if m:
            return m.group(1).replace('\\u0026', '&').replace('&amp;', '&')
        m = re.search(r'"profile_pic_url"\s*:\s*"([^"]+)"', text)
        if m:
            return m.group(1).replace('\\u0026', '&').replace('&amp;', '&')
        img_alt = re.search(
            r'alt="Foto do perfil de [^"]*"[^>]*\ssrc="([^"]+)"',
            text,
            re.I,
        ) or re.search(
            r'src="([^"]+)"[^>]*alt="Foto do perfil de',
            text,
            re.I,
        )
        if img_alt:
            return img_alt.group(1).replace('&amp;', '&')
        fbcdn = re.search(
            r'https://[^\s"\']*(?:fbcdn\.net|cdninstagram\.com)[^\s"\']*t51\.2885-19[^\s"\']*',
            text,
            re.I,
        )
        if fbcdn:
            return fbcdn.group(0).replace('\\u0026', '&').replace('&amp;', '&')
    except Exception as e:
        logger.debug('[Instagram] Falha ao buscar foto de %s: %s', handle, e)
    return None


def fetch_instagram_profile(handle: str) -> dict:
    """Busca o HTML público do perfil e extrai o máximo de campos sem login.

    Retorna um dict (possivelmente vazio) com chaves: profile_picture_url,
    full_name, biography, external_url, follower_count, post_count, email,
    phone, is_verified, is_business_account.
    """
    handle = handle.lstrip('@')
    url = f'https://www.instagram.com/{handle}/'
    out: dict = {}
    try:
        resp = requests.get(url, headers=_headers(), timeout=9)
        if resp.status_code != 200:
            return out
        text = resp.text
    except Exception as e:
        logger.debug('[Instagram] Falha ao buscar perfil %s: %s', handle, e)
        return out

    def _first(*patterns):
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return _clean_unicode(m.group(1)).strip()
        return None

    pic = _first(
        r'"profile_pic_url_hd"\s*:\s*"([^"]+)"',
        r'"profile_pic_url"\s*:\s*"([^"]+)"',
    )
    if not pic:
        pic = fetch_instagram_profile_pic(handle)
    if pic:
        out['profile_picture_url'] = pic

    full_name = _first(r'"full_name"\s*:\s*"([^"]*)"')
    if full_name:
        out['full_name'] = full_name

    bio = _first(r'"biography"\s*:\s*"((?:[^"\\]|\\.)*)"')
    if bio:
        try:
            bio = bio.encode('utf-8').decode('unicode_escape')
        except Exception:
            pass
        out['biography'] = bio

    external = _first(r'"external_url"\s*:\s*"([^"]+)"')
    if external:
        out['external_url'] = external

    followers = _first(r'"edge_followed_by"\s*:\s*\{\s*"count"\s*:\s*(\d+)')
    if followers:
        try:
            out['follower_count'] = int(followers)
        except ValueError:
            pass

    posts = _first(r'"edge_owner_to_timeline_media"\s*:\s*\{\s*"count"\s*:\s*(\d+)')
    if posts:
        try:
            out['post_count'] = int(posts)
        except ValueError:
            pass

    email = _first(r'"business_email"\s*:\s*"([^"]+)"', r'"public_email"\s*:\s*"([^"]+)"')
    if not email:
        for source in (out.get('biography', ''), text[:20000]):
            m = EMAIL_RE.search(source or '')
            if m:
                email = m.group(0)
                break
    if email and EMAIL_RE.fullmatch(email):
        out['email'] = email

    phone = _first(
        r'"business_phone_number"\s*:\s*"([^"]+)"',
        r'"contact_phone_number"\s*:\s*"([^"]+)"',
        r'"public_phone_number"\s*:\s*"([^"]+)"',
    )
    if phone:
        out['phone'] = phone

    if re.search(r'"is_verified"\s*:\s*true', text):
        out['is_verified'] = True
    if re.search(r'"is_business_account"\s*:\s*true', text) or re.search(
        r'"is_professional_account"\s*:\s*true', text
    ):
        out['is_business_account'] = True

    return out


def _parse_ddg_html(text: str) -> list[dict]:
    soup = BeautifulSoup(text, 'html.parser')
    results = []
    for result in soup.select('.result'):
        title_el = result.select_one('.result__title a')
        snippet_el = result.select_one('.result__snippet')
        if not title_el:
            continue
        href = title_el.get('href', '')
        parsed = urllib.parse.urlparse(href)
        if parsed.path == '/l/':
            qs = urllib.parse.parse_qs(parsed.query)
            href = qs.get('uddg', [href])[0]
        results.append({
            'url': href,
            'snippet': snippet_el.get_text(strip=True) if snippet_el else '',
        })
    return results


def _search_duckduckgo(query: str) -> list[dict]:
    try:
        resp = requests.post(
            'https://html.duckduckgo.com/html/',
            headers=_headers(),
            data={'q': query},
            timeout=10,
        )
        return _parse_ddg_html(resp.text)
    except Exception as e:
        logger.warning('[Instagram DDG] Erro: %s', e)
        return []


def _search_bing(query: str) -> list[dict]:
    """Fallback de busca quando o DuckDuckGo traz pouca coisa."""
    try:
        resp = requests.get(
            'https://www.bing.com/search',
            headers=_headers(),
            params={'q': query, 'count': 20, 'setlang': 'pt-BR'},
            timeout=10,
        )
        soup = BeautifulSoup(resp.text, 'html.parser')
        results = []
        for li in soup.select('li.b_algo'):
            link = li.select_one('h2 a')
            if not link:
                continue
            snippet_el = li.select_one('.b_caption p') or li.select_one('p')
            results.append({
                'url': link.get('href', ''),
                'snippet': snippet_el.get_text(strip=True) if snippet_el else '',
            })
        return results
    except Exception as e:
        logger.warning('[Instagram Bing] Erro: %s', e)
        return []


def _handle_from_url(url: str) -> str | None:
    if 'instagram.com' not in (url or ''):
        return None
    parts = [p for p in urllib.parse.urlparse(url).path.split('/') if p]
    if not parts:
        return None
    handle = parts[0].lstrip('@').lower()
    if not handle or handle in SKIP_HANDLES:
        return None
    if not re.fullmatch(r'[a-z0-9._]{1,40}', handle):
        return None
    return handle


def _existing_handles(user) -> set[str]:
    from .models import Lead
    raw = (
        Lead.objects.filter(user=user, source='instagram')
        .exclude(instagram__isnull=True)
        .exclude(instagram='')
        .values_list('instagram', flat=True)
    )
    return {str(h).strip().lstrip('@').lower() for h in raw if h}


def run_instagram_scraper(
    user,
    niche: str,
    location: str | None = None,
    limit: int = 10,
    only_verified: bool = False,
    only_with_bio_link: bool = False,
    seed=None,
) -> tuple[int, int]:
    city = location or 'Brasil'
    leads_data: list[dict] = []
    seen_handles: set[str] = set(_existing_handles(user))

    # Variações de busca para ampliar a cobertura (sem login, server-side).
    if location:
        queries = [
            f'site:instagram.com "{niche}" "{location}"',
            f'site:instagram.com "{niche}" {location}',
            f'site:instagram.com {niche} {location} whatsapp',
            f'site:instagram.com {niche} {location} contato',
        ]
    else:
        queries = [
            f'site:instagram.com "{niche}"',
            f'site:instagram.com {niche} whatsapp',
        ]

    candidates: list[dict] = []
    candidate_handles: set[str] = set()

    def _collect(results):
        for r in results:
            handle = _handle_from_url(r.get('url', ''))
            if not handle or handle in candidate_handles or handle in seen_handles:
                continue
            candidate_handles.add(handle)
            candidates.append({'handle': handle, 'snippet': r.get('snippet', '')})

    for query in queries:
        if len(candidates) >= limit * 3:
            break
        _collect(_search_duckduckgo(query))
        time.sleep(random.uniform(1.2, 2.6))

    # Fallback: só aciona o Bing se o DuckDuckGo trouxe pouca coisa.
    if len(candidates) < limit:
        for query in queries[:2]:
            if len(candidates) >= limit * 2:
                break
            _collect(_search_bing(query))
            time.sleep(random.uniform(1.2, 2.6))

    for cand in candidates:
        if len(leads_data) >= limit:
            break
        handle = cand['handle']
        snippet = cand['snippet']

        profile = fetch_instagram_profile(handle) or {}

        name = profile.get('full_name') or handle.replace('.', ' ').replace('_', ' ').title()

        phone_raw = profile.get('phone')
        if not phone_raw:
            phone_m = re.search(r'\(?\d{2}\)?\s?(?:9\s?\d{4}|\d{4})[-\s]?\d{4}', snippet)
            phone_raw = phone_m.group(0) if phone_m else None
        norm_phone = normalize_phone(phone_raw) if phone_raw else None

        website_raw = profile.get('external_url')
        if not website_raw:
            site_m = re.search(r'https?://(?!(?:www\.)?instagram)[^\s"\'<>]{4,80}', snippet)
            website_raw = site_m.group(0).rstrip('.,)') if site_m else None
        website_type = detect_website_type(website_raw)
        website = website_raw if website_type == 'website' else None

        email = profile.get('email')
        bio = profile.get('biography') or snippet[:250]

        if only_with_bio_link and not (website_raw or email or norm_phone):
            continue

        is_verified = bool(profile.get('is_verified')) or only_verified
        if only_verified and not is_verified:
            continue

        amenities = {}
        if profile.get('follower_count') is not None:
            amenities['follower_count'] = profile['follower_count']
        if profile.get('post_count') is not None:
            amenities['post_count'] = profile['post_count']
        if profile.get('is_business_account'):
            amenities['is_business_account'] = True
        if email:
            amenities['email'] = email
        if norm_phone:
            amenities['whatsapp_number'] = norm_phone
            amenities['is_whatsapp_linked'] = True

        leads_data.append({
            'name': name,
            'category': niche.title(),
            'city': city,
            'phone_number': phone_raw,
            'normalized_phone': norm_phone,
            'email': email,
            'website': website,
            'website_detected_type': website_type,
            'instagram': f'@{handle}',
            'bio': bio[:250],
            'source': 'instagram',
            'status': 'novo',
            'is_verified': is_verified,
            'profile_picture_url': profile.get('profile_picture_url'),
            'amenities': amenities or None,
        })
        time.sleep(random.uniform(0.8, 1.8))

    if not leads_data:
        logger.warning("[Instagram] Nenhum perfil encontrado para '%s' em '%s'.", niche, city)

    saved, skipped, _updated, _reasons = save_leads_from_dicts(user, leads_data[:limit])
    return saved, skipped
