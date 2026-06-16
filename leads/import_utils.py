"""Utilitários compartilhados para importação de leads (extensão, CSV, scraper)."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from django.db.models import Q

from .models import Lead
from .profile_picture_utils import apply_profile_picture_from_import
from .website_utils import detect_website_type


def _normalize_instagram_handle(inst: str | None) -> str | None:
    if not inst:
        return None
    handle = str(inst).strip().lstrip('@').lower()
    return handle or None


def _format_phone_br(normalized: str | None) -> str | None:
    if not normalized:
        return None
    digits = ''.join(c for c in str(normalized) if c.isdigit())
    if digits.startswith('55') and len(digits) > 11:
        digits = digits[2:]
    if len(digits) == 11:
        return f'({digits[:2]}) {digits[2:7]}-{digits[7:]}'
    if len(digits) == 10:
        return f'({digits[:2]}) {digits[2:6]}-{digits[6:]}'
    return normalized


def _normalize_maps_url(url: str | None) -> str | None:
    if not url:
        return None
    raw = str(url).strip()
    if raw.startswith('/maps/place/'):
        path = raw.split('?')[0]
    else:
        try:
            path = urlparse(raw).path
        except Exception:
            return None
    decoded = unquote(path)
    match = re.match(r'(/maps/place/[^/]+)', decoded, re.IGNORECASE)
    if match:
        return match.group(1).lower().rstrip('/')
    return None


def _find_instagram_lead(user, inst_norm: str):
    return Lead.objects.filter(user=user).filter(
        Q(instagram__iexact=f'@{inst_norm}') | Q(instagram__iexact=inst_norm)
    ).first()


def _find_maps_lead(user, maps_norm: str) -> Lead | None:
    if not maps_norm:
        return None
    slug = maps_norm.rsplit('/', 1)[-1].lower()
    candidates = Lead.objects.filter(user=user).exclude(
        Q(maps_url__isnull=True) | Q(maps_url='')
    ).filter(maps_url__icontains=slug)
    for lead in candidates:
        if _normalize_maps_url(lead.maps_url) == maps_norm:
            return lead
    return None


def _update_instagram_lead(existing: Lead, item: dict) -> None:
    """Atualiza lead existente com dados mais recentes da extensão Instagram."""
    amenities = item.get('_amenities') or item.get('amenities')
    if amenities and isinstance(amenities, dict):
        if isinstance(existing.amenities, dict):
            merged = {**existing.amenities, **amenities}
            for key in ('recent_posts', 'recent_reels', 'latest_post'):
                new_val = amenities.get(key)
                old_val = existing.amenities.get(key)
                if (not new_val or (isinstance(new_val, list) and len(new_val) == 0)) and old_val:
                    merged[key] = old_val
            existing.amenities = merged
        else:
            existing.amenities = amenities
    if item.get('bio'):
        existing.bio = item['bio']
    apply_profile_picture_from_import(existing, item)
    if item.get('_total_photos') or item.get('total_photos'):
        existing.total_photos = item.get('_total_photos') or item.get('total_photos')
    if item.get('category'):
        existing.category = item['category']
    if item.get('city') and not existing.city:
        existing.city = item['city']
    if item.get('address'):
        existing.address = item['address']
    if item.get('website'):
        existing.website = item['website']
    if item.get('website_detected_type'):
        existing.website_detected_type = item['website_detected_type']
    for field in ('facebook', 'youtube', 'twitter', 'linkedin'):
        if item.get(field):
            setattr(existing, field, item[field])
    if item.get('phone_number'):
        existing.phone_number = item['phone_number']
    if item.get('normalized_phone'):
        existing.normalized_phone = item['normalized_phone']
    if not existing.phone_number and existing.normalized_phone:
        existing.phone_number = _format_phone_br(existing.normalized_phone)
    if item.get('is_verified') is not None:
        existing.is_verified = item['is_verified']
    existing.save()


def _update_maps_lead(existing: Lead, item: dict) -> None:
    """Atualiza lead Google Maps existente com dados mais recentes da extensão."""
    if item.get('name'):
        existing.name = item['name']
    if item.get('category'):
        existing.category = item['category']
    if item.get('city'):
        existing.city = item['city']
    if item.get('address'):
        existing.address = item['address']
    if item.get('phone_number'):
        existing.phone_number = item['phone_number']
    if item.get('normalized_phone'):
        existing.normalized_phone = item['normalized_phone']
    if not existing.phone_number and existing.normalized_phone:
        existing.phone_number = _format_phone_br(existing.normalized_phone)
    if item.get('website'):
        existing.website = item['website']
    if item.get('website_detected_type'):
        existing.website_detected_type = item['website_detected_type']
    for field in ('instagram', 'facebook', 'youtube', 'twitter', 'linkedin'):
        if item.get(field):
            setattr(existing, field, item[field])
    if item.get('bio'):
        existing.bio = item['bio']
    if item.get('rating') is not None:
        existing.rating = item['rating']
    if item.get('review_count') is not None:
        existing.review_count = item['review_count']
    if item.get('recent_reviews'):
        existing.recent_reviews = item['recent_reviews']
    if item.get('business_hours'):
        existing.business_hours = item['business_hours']
    if item.get('maps_url'):
        existing.maps_url = item['maps_url']
    if item.get('maps_share_url'):
        existing.maps_share_url = item['maps_share_url']
    if item.get('_price_range') or item.get('price_range'):
        existing.price_range = item.get('_price_range') or item.get('price_range')
    if item.get('_plus_code') or item.get('plus_code'):
        existing.plus_code = item.get('_plus_code') or item.get('plus_code')
    amenities = item.get('_amenities') or item.get('amenities')
    if amenities:
        existing.amenities = amenities
    if item.get('_total_photos') or item.get('total_photos'):
        existing.total_photos = item.get('_total_photos') or item.get('total_photos')
    apply_profile_picture_from_import(existing, item)
    existing.save()


def _is_duplicate_google_maps(user, name: str, norm_p: str | None, city: str, maps_norm: str | None) -> tuple[bool, str | None]:
    if norm_p and maps_norm:
        for other in Lead.objects.filter(user=user, normalized_phone=norm_p):
            other_maps = _normalize_maps_url(other.maps_url)
            if other_maps and other_maps == maps_norm:
                return True, 'duplicate_phone'
    elif norm_p:
        if Lead.objects.filter(user=user, normalized_phone=norm_p, maps_url__isnull=True).exists():
            return True, 'duplicate_phone'
        if Lead.objects.filter(user=user, normalized_phone=norm_p, maps_url='').exists():
            return True, 'duplicate_phone'

    if city:
        if Lead.objects.filter(user=user, name__iexact=name, city__iexact=city).exists():
            return True, 'duplicate_name_city'
    elif Lead.objects.filter(user=user, name__iexact=name).exists():
        return True, 'duplicate_name'

    return False, None


def _is_duplicate_generic(user, name: str, norm_p: str | None, inst: str | None, inst_norm: str | None) -> tuple[bool, str | None]:
    if norm_p and Lead.objects.filter(user=user, normalized_phone=norm_p).exists():
        return True, 'duplicate_phone'
    if Lead.objects.filter(user=user, name__iexact=name).exists():
        return True, 'duplicate_name'
    if inst and Lead.objects.filter(user=user, instagram__iexact=inst, name__iexact=name).exists():
        return True, 'duplicate_instagram_name'
    if inst_norm:
        existing_ig = _find_instagram_lead(user, inst_norm)
        if existing_ig:
            return True, 'duplicate_instagram'
    return False, None


def save_leads_from_dicts(user, leads: list[dict]) -> tuple[int, int, int, dict]:
    """
    Salva leads no banco com deduplicação.
    Retorna (saved, skipped, updated, skipped_reasons).
    """
    saved = skipped = updated = 0
    skipped_reasons: dict[str, int] = {}

    def _skip(reason: str) -> None:
        nonlocal skipped
        skipped += 1
        skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1

    for item in leads:
        norm_p = item.get('normalized_phone')
        inst = item.get('instagram')
        name = (item.get('name') or '').strip()
        source = item.get('source', 'google_maps')
        city = (item.get('city') or '').strip()
        maps_norm = _normalize_maps_url(item.get('maps_url')) or _normalize_maps_url(item.get('_place_key'))

        if not name:
            _skip('empty_name')
            continue

        inst_norm = _normalize_instagram_handle(inst)
        if inst_norm:
            existing_ig = _find_instagram_lead(user, inst_norm)
            if existing_ig and (source == 'instagram' or existing_ig.source == 'instagram'):
                _update_instagram_lead(existing_ig, item)
                saved += 1
                continue

        if source == 'google_maps' and maps_norm:
            existing_maps = _find_maps_lead(user, maps_norm)
            if existing_maps:
                _update_maps_lead(existing_maps, item)
                updated += 1
                continue

        if not norm_p and item.get('phone_number'):
            norm_p = _normalize_phone_local(item['phone_number'])

        website = item.get('website')
        website_type = item.get('website_detected_type')
        if website and not website_type:
            website_type = detect_website_type(website)

        if source == 'google_maps':
            dup, reason = _is_duplicate_google_maps(user, name, norm_p, city, maps_norm)
        else:
            dup, reason = _is_duplicate_generic(user, name, norm_p, inst, inst_norm)

        if dup:
            _skip(reason or 'duplicate')
            continue

        lead = Lead.objects.create(
            user=user,
            name=name,
            category=item.get('category') or '',
            city=city,
            phone_number=item.get('phone_number'),
            normalized_phone=norm_p,
            website=website,
            website_detected_type=website_type,
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
            source=source,
            status=item.get('status', 'novo'),
            is_verified=item.get('is_verified', False),
            price_range=item.get('_price_range') or item.get('price_range'),
            plus_code=item.get('_plus_code') or item.get('plus_code'),
            amenities=item.get('_amenities') or item.get('amenities') or None,
            total_photos=item.get('_total_photos') or item.get('total_photos'),
        )
        apply_profile_picture_from_import(lead, item)
        saved += 1

    return saved, skipped, updated, skipped_reasons


def _normalize_phone_local(phone: str) -> str | None:
    digits = re.sub(r'\D', '', str(phone))
    if not digits:
        return None
    if digits.startswith('55') and len(digits) > 12:
        digits = digits[2:]
    if len(digits) < 8:
        return None
    if len(digits) <= 11:
        digits = '55' + digits
    return digits


def parse_leads_upload(content: str, filename: str) -> list[dict]:
    """Parseia JSON ou CSV exportado pela extensão."""
    import csv
    import json

    name_lower = (filename or '').lower()
    if name_lower.endswith('.json'):
        data = json.loads(content)
        if isinstance(data, dict) and 'leads' in data:
            return data['leads']
        if isinstance(data, list):
            return data
        raise ValueError('JSON inválido: esperado lista ou {"leads": [...]}')

    if name_lower.endswith('.csv'):
        reader = csv.DictReader(content.splitlines())
        leads = []
        for row in reader:
            lead = dict(row)
            for json_field in ('business_hours', 'recent_reviews', '_amenities'):
                if lead.get(json_field):
                    try:
                        lead[json_field] = json.loads(lead[json_field])
                    except (json.JSONDecodeError, TypeError):
                        pass
            if lead.get('rating'):
                try:
                    lead['rating'] = float(str(lead['rating']).replace(',', '.'))
                except ValueError:
                    lead['rating'] = None
            if lead.get('review_count'):
                try:
                    lead['review_count'] = int(str(lead['review_count']).replace('.', '').replace(',', ''))
                except ValueError:
                    lead['review_count'] = 0
            leads.append(lead)
        return leads

    raise ValueError('Formato não suportado. Use .json ou .csv')
