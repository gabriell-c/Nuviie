"""Persistência e proxy de fotos de perfil Instagram (gratuito, local)."""

from __future__ import annotations

import base64
import logging
import re
from typing import TYPE_CHECKING

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

if TYPE_CHECKING:
    from .models import Lead

logger = logging.getLogger(__name__)

AVATAR_DIR = 'lead_avatars'
MAX_BYTES = 500_000

IG_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Referer': 'https://www.instagram.com/',
    'Accept-Language': 'pt-BR,pt;q=0.9',
}


def _public_base_url() -> str:
    return getattr(settings, 'NUVIIE_PUBLIC_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')


def public_media_url(relative_path: str) -> str:
    media = settings.MEDIA_URL.strip('/')
    rel = relative_path.lstrip('/')
    return f'{_public_base_url()}/{media}/{rel}'


def avatar_storage_path(handle: str, ext: str = 'jpg') -> str:
    safe = re.sub(r'[^\w.-]', '_', str(handle).lstrip('@').lower())
    return f'{AVATAR_DIR}/{safe}.{ext}'


def normalize_handle_from_item(item: dict, lead: Lead | None = None) -> str:
    inst = item.get('instagram') or (lead.instagram if lead else None) or (lead.name if lead else 'lead')
    return str(inst).lstrip('@').lower()


def is_cdn_profile_url(url: str | None) -> bool:
    if not url:
        return False
    u = url.lower()
    return 'fbcdn.net' in u or 'cdninstagram.com' in u


def is_local_media_url(url: str | None) -> bool:
    if not url:
        return False
    u = url.lower()
    return 'lead_avatars' in u or '/media/' in u


def get_lead_avatar_storage_path(lead: Lead) -> str | None:
    handle = str(lead.instagram or lead.name or lead.pk).lstrip('@').lower()
    for ext in ('jpg', 'jpeg', 'png', 'webp'):
        path = avatar_storage_path(handle, ext)
        if default_storage.exists(path):
            return path
    return None


def _guess_ext(content_type: str, data_url_header: str = '') -> str:
    ct = (content_type or '').lower()
    header = (data_url_header or '').lower()
    if 'png' in ct or 'png' in header:
        return 'png'
    if 'webp' in ct or 'webp' in header:
        return 'webp'
    return 'jpg'


def save_lead_profile_picture_from_data_url(
    lead: Lead,
    data_url: str | None,
    handle: str | None = None,
) -> str | None:
    if not data_url or not str(data_url).startswith('data:image'):
        return None
    handle = handle or normalize_handle_from_item({}, lead)
    try:
        header, b64 = str(data_url).split(',', 1)
        ext = _guess_ext('', header)
        raw = base64.b64decode(b64)
        if len(raw) > MAX_BYTES or len(raw) < 50:
            return None
        path = avatar_storage_path(handle, ext)
        if default_storage.exists(path):
            default_storage.delete(path)
        saved = default_storage.save(path, ContentFile(raw))
        return public_media_url(saved)
    except Exception as exc:
        logger.debug('[Avatar] Falha ao salvar data URL para %s: %s', handle, exc)
        return None


def fetch_and_cache_profile_picture(
    lead: Lead,
    url: str | None,
    handle: str | None = None,
) -> str | None:
    if not url:
        return None
    if is_local_media_url(url):
        return url

    handle = handle or normalize_handle_from_item({}, lead)
    existing = get_lead_avatar_storage_path(lead)
    if existing:
        return public_media_url(existing)

    try:
        resp = requests.get(url, headers=IG_HEADERS, timeout=12)
        if resp.status_code != 200:
            return None
        content = resp.content
        if len(content) > MAX_BYTES or len(content) < 50:
            return None
        ext = _guess_ext(resp.headers.get('content-type', ''))
        path = avatar_storage_path(handle, ext)
        saved = default_storage.save(path, ContentFile(content))
        return public_media_url(saved)
    except Exception as exc:
        logger.debug('[Avatar] Falha ao baixar CDN para %s: %s', handle, exc)
        return None


def apply_profile_picture_from_import(lead: Lead, item: dict) -> None:
    """Salva foto local a partir de base64 ou URL CDN e atualiza o lead."""
    handle = normalize_handle_from_item(item, lead)
    data_url = item.get('profile_picture_data')
    cdn_url = item.get('profile_picture_url')

    local_url = None
    if data_url:
        local_url = save_lead_profile_picture_from_data_url(lead, data_url, handle)
    if not local_url and cdn_url:
        local_url = fetch_and_cache_profile_picture(lead, cdn_url, handle)

    if local_url:
        lead.profile_picture_url = local_url
        lead.save(update_fields=['profile_picture_url'])
    elif cdn_url:
        lead.profile_picture_url = cdn_url
        lead.save(update_fields=['profile_picture_url'])


def fallback_post_image_url(lead: Lead) -> str | None:
    amenities = lead.amenities if isinstance(lead.amenities, dict) else {}
    for key in ('recent_posts', 'recent_reels'):
        items = amenities.get(key) or []
        if isinstance(items, list):
            for post in items:
                if isinstance(post, dict) and post.get('image_url'):
                    return post['image_url']
    return None


def get_profile_picture_display_url(lead: Lead, request=None) -> str | None:
    url = lead.profile_picture_url
    if url and is_local_media_url(url):
        return url
    if url and is_cdn_profile_url(url):
        if request:
            return request.build_absolute_uri(f'/api/leads/{lead.pk}/avatar/')
        return f'{_public_base_url()}/api/leads/{lead.pk}/avatar/'
    if url:
        return url
    return fallback_post_image_url(lead)


def read_avatar_bytes(lead: Lead) -> tuple[bytes, str] | None:
    """Retorna (bytes, content_type) do avatar local ou None."""
    path = get_lead_avatar_storage_path(lead)
    if path:
        with default_storage.open(path, 'rb') as fh:
            content = fh.read()
        ext = path.rsplit('.', 1)[-1].lower()
        ctype = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'webp': 'image/webp',
        }.get(ext, 'image/jpeg')
        return content, ctype
    return None
