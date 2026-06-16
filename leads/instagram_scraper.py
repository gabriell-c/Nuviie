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
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
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
        except Exception as e:
            logger.warning('[Instagram DDG] Erro: %s', e)
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
            name = handle.replace('.', ' ').replace('_', ' ').title()
            phone_m = re.search(r'\(?\d{2}\)?\s?(?:9\s?\d{4}|\d{4})[-\s]?\d{4}', snippet)
            phone_raw = phone_m.group(0) if phone_m else None
            norm_phone = normalize_phone(phone_raw) if phone_raw else None
            site_m = re.search(r'https?://(?!(?:www\.)?instagram)[^\s"\'<>]{4,80}', snippet)
            website_raw = site_m.group(0).rstrip('.,)') if site_m else None
            website_type = detect_website_type(website_raw)
            website = website_raw if website_type == 'website' else None

            if only_with_bio_link and not website_raw:
                continue

            pic_url = fetch_instagram_profile_pic(handle)
            leads_data.append({
                'name': name,
                'category': niche.title(),
                'city': city,
                'phone_number': phone_raw,
                'normalized_phone': norm_phone,
                'website': website,
                'website_detected_type': website_type,
                'instagram': f'@{handle}',
                'bio': snippet[:250],
                'source': 'instagram',
                'status': 'novo',
                'is_verified': only_verified,
                'profile_picture_url': pic_url,
            })

    if not leads_data:
        logger.warning("[Instagram] Nenhum perfil encontrado para '%s' em '%s'.", niche, city)

    saved, skipped, _updated, _reasons = save_leads_from_dicts(user, leads_data[:limit])
    return saved, skipped
