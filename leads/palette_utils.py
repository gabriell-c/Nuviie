"""Extração e CRUD de paleta de cores (3–5) associada ao lead."""

from __future__ import annotations

import base64
import io
import logging
import re
from typing import TYPE_CHECKING

import requests
from django.utils import timezone

from .profile_picture_utils import (
    IG_HEADERS,
    fallback_post_image_url,
    fetch_and_cache_profile_picture,
    read_avatar_bytes,
)

if TYPE_CHECKING:
    from .models import Lead

logger = logging.getLogger(__name__)

MIN_COLORS = 3
MAX_COLORS = 5
HEX_RE = re.compile(r'^#?[0-9A-Fa-f]{6}$')


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f'#{r:02x}{g:02x}{b:02x}'.upper()


def _vary_rgb(r: int, g: int, b: int, factor: float) -> tuple[int, int, int]:
    return (
        max(0, min(255, int(r * factor))),
        max(0, min(255, int(g * factor))),
        max(0, min(255, int(b * factor))),
    )


def _color_entry(rgb: tuple[int, int, int], prominence: float) -> dict:
    r, g, b = rgb
    return {
        'hex': _rgb_to_hex(r, g, b),
        'rgb': [r, g, b],
        'prominence': round(prominence, 4),
    }


def _ensure_amenities_dict(lead: Lead) -> dict:
    if isinstance(lead.amenities, dict):
        return dict(lead.amenities)
    if isinstance(lead.amenities, list):
        return {'legacy_list': lead.amenities}
    return {}


def normalize_hex(value: str) -> str:
    raw = (value or '').strip().upper()
    if not raw.startswith('#'):
        raw = f'#{raw}'
    if not HEX_RE.match(raw):
        raise ValueError('Cor inválida. Use formato hexadecimal (#RRGGBB).')
    return raw


def color_from_hex(value: str, *, prominence: float = 0.5) -> dict:
    hex_v = normalize_hex(value)
    r = int(hex_v[1:3], 16)
    g = int(hex_v[3:5], 16)
    b = int(hex_v[5:7], 16)
    return _color_entry((r, g, b), prominence)


def normalize_colors_list(colors: list) -> list[dict]:
    if not isinstance(colors, list):
        raise ValueError('Lista de cores inválida.')
    if len(colors) > MAX_COLORS:
        raise ValueError(f'Máximo de {MAX_COLORS} cores por paleta.')
    out: list[dict] = []
    seen: set[str] = set()
    for idx, item in enumerate(colors):
        if isinstance(item, str):
            entry = color_from_hex(item, prominence=max(0.1, 1.0 - idx * 0.15))
        elif isinstance(item, dict):
            hex_v = normalize_hex(item.get('hex') or '')
            if hex_v in seen:
                continue
            base = color_from_hex(hex_v, prominence=float(item.get('prominence') or max(0.1, 1.0 - idx * 0.15)))
            if item.get('rgb') and len(item['rgb']) == 3:
                base['rgb'] = [int(x) for x in item['rgb']]
            entry = base
        else:
            raise ValueError('Cada cor deve ser um hex ou objeto { hex, rgb? }.')
        if entry['hex'] in seen:
            continue
        seen.add(entry['hex'])
        out.append(entry)
    return out


def get_stored_palette(lead: Lead) -> dict | None:
    amenities = lead.amenities if isinstance(lead.amenities, dict) else {}
    palette = amenities.get('color_palette')
    return palette if isinstance(palette, dict) else None


def persist_palette(lead: Lead, colors: list[dict], *, source: str) -> dict:
    amenities = _ensure_amenities_dict(lead)
    palette_data = {
        'colors': colors,
        'extracted_at': timezone.now().isoformat(),
        'source': source,
    }
    amenities['color_palette'] = palette_data
    lead.amenities = amenities
    lead.save(update_fields=['amenities'])
    return palette_data


def save_palette(lead: Lead, colors: list, *, source: str = 'manual') -> dict:
    normalized = normalize_colors_list(colors)
    if not normalized:
        raise ValueError('Informe ao menos uma cor.')
    return persist_palette(lead, normalized, source=source)


def clear_palette(lead: Lead) -> None:
    amenities = _ensure_amenities_dict(lead)
    amenities.pop('color_palette', None)
    lead.amenities = amenities
    lead.save(update_fields=['amenities'])


def add_palette_color(lead: Lead, hex_value: str) -> dict:
    palette = get_stored_palette(lead) or {'colors': [], 'source': 'manual'}
    colors = list(palette.get('colors') or [])
    if len(colors) >= MAX_COLORS:
        raise ValueError(f'Máximo de {MAX_COLORS} cores por paleta.')
    entry = color_from_hex(hex_value, prominence=max(0.1, 1.0 - len(colors) * 0.15))
    if any(c.get('hex') == entry['hex'] for c in colors):
        raise ValueError('Esta cor já está na paleta.')
    colors.append(entry)
    return persist_palette(lead, colors, source=palette.get('source') or 'manual')


def update_palette_color(lead: Lead, index: int, hex_value: str) -> dict:
    palette = get_stored_palette(lead)
    if not palette:
        raise ValueError('Nenhuma paleta cadastrada para este lead.')
    colors = list(palette.get('colors') or [])
    if index < 0 or index >= len(colors):
        raise ValueError('Índice de cor inválido.')
    entry = color_from_hex(hex_value, prominence=colors[index].get('prominence') or 0.5)
    if any(i != index and c.get('hex') == entry['hex'] for i, c in enumerate(colors)):
        raise ValueError('Esta cor já está na paleta.')
    colors[index] = entry
    return persist_palette(lead, colors, source=palette.get('source') or 'manual')


def delete_palette_color(lead: Lead, index: int) -> dict | None:
    palette = get_stored_palette(lead)
    if not palette:
        raise ValueError('Nenhuma paleta cadastrada para este lead.')
    colors = list(palette.get('colors') or [])
    if index < 0 or index >= len(colors):
        raise ValueError('Índice de cor inválido.')
    colors.pop(index)
    if not colors:
        clear_palette(lead)
        return None
    return persist_palette(lead, colors, source=palette.get('source') or 'manual')


def extract_palette(
    image_bytes: bytes,
    *,
    min_colors: int = MIN_COLORS,
    max_colors: int = MAX_COLORS,
) -> list[dict]:
    """Extrai entre min_colors e max_colors cores dominantes."""
    if not image_bytes or len(image_bytes) < 50:
        raise ValueError('Imagem inválida ou muito pequena.')

    try:
        from colorthief import ColorThief
    except ImportError as exc:
        raise ValueError(
            'Biblioteca de extração de cores não instalada (colorthief). '
            'Rode: pip install colorthief'
        ) from exc

    thief = ColorThief(io.BytesIO(image_bytes))
    raw = thief.get_palette(color_count=max_colors, quality=1) or []
    if not raw:
        dominant = thief.get_color(quality=1)
        raw = [dominant]

    total = len(raw)
    colors: list[dict] = []
    for idx, rgb in enumerate(raw[:max_colors]):
        prominence = max(0.05, 1.0 - (idx / max(total, 1)) * 0.85)
        colors.append(_color_entry(rgb, prominence))

    if len(colors) < min_colors and colors:
        base = colors[0]['rgb']
        factors = [0.75, 1.25, 0.55, 1.45]
        for factor in factors:
            if len(colors) >= min_colors:
                break
            varied = _vary_rgb(base[0], base[1], base[2], factor)
            hex_v = _rgb_to_hex(*varied)
            if not any(c['hex'] == hex_v for c in colors):
                colors.append(_color_entry(varied, 0.15))

    return colors[:max_colors]


def decode_image_data(data: str) -> bytes:
    """Decodifica imagem colada (data URI base64) em bytes."""
    if not data:
        raise ValueError('Nenhuma imagem colada.')
    raw_str = data.strip()
    if raw_str.startswith('data:'):
        if ',' not in raw_str:
            raise ValueError('Imagem colada inválida.')
        raw_str = raw_str.split(',', 1)[1]
    try:
        raw = base64.b64decode(raw_str, validate=False)
    except Exception as exc:
        raise ValueError('Imagem colada inválida.') from exc
    if len(raw) < 50:
        raise ValueError('Imagem colada inválida ou muito pequena.')
    if len(raw) > 5_000_000:
        raise ValueError('Imagem colada muito grande (máx 5MB).')
    return raw


def _fetch_url_bytes(url: str) -> bytes | None:
    try:
        resp = requests.get(url, headers=IG_HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        content = resp.content
        if len(content) < 50 or len(content) > 2_000_000:
            return None
        return content
    except Exception as exc:
        logger.debug('[Palette] Falha ao baixar URL: %s', exc)
        return None


def get_lead_image_bytes(lead: Lead, image_url: str | None = None) -> tuple[bytes, str]:
    """
    Retorna (bytes, source) da imagem para extração.
    source: profile_picture | custom_url | post_image
    """
    if image_url:
        data = _fetch_url_bytes(image_url)
        if data:
            return data, 'custom_url'
        raise ValueError('Não foi possível baixar a imagem da URL informada.')

    cached = read_avatar_bytes(lead)
    if cached:
        return cached[0], 'profile_picture'

    if lead.profile_picture_url:
        local = fetch_and_cache_profile_picture(lead, lead.profile_picture_url)
        if local:
            lead.profile_picture_url = local
            lead.save(update_fields=['profile_picture_url'])
            cached = read_avatar_bytes(lead)
            if cached:
                return cached[0], 'profile_picture'
        data = _fetch_url_bytes(lead.profile_picture_url)
        if data:
            return data, 'profile_picture'

    post_url = fallback_post_image_url(lead)
    if post_url:
        data = _fetch_url_bytes(post_url)
        if data:
            return data, 'post_image'

    raise ValueError('Nenhuma imagem disponível para este lead.')


def extract_and_store_palette(
    lead: Lead,
    image_url: str | None = None,
    image_data: str | None = None,
) -> dict:
    """Extrai paleta e persiste em lead.amenities['color_palette'].

    image_data: imagem colada/enviada como data URI base64 (Ctrl+V, arrastar, upload).
    """
    if image_data:
        image_bytes = decode_image_data(image_data)
        source = 'pasted_image'
    else:
        image_bytes, source = get_lead_image_bytes(lead, image_url)
    colors = extract_palette(image_bytes)
    return persist_palette(lead, colors, source=source)
