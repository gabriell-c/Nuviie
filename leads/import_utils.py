"""Utilitários compartilhados para importação de leads (extensão, CSV, scraper)."""

from __future__ import annotations

from .models import Lead
from .website_utils import detect_website_type


def save_leads_from_dicts(user, leads: list[dict]) -> tuple[int, int]:
    """
    Salva leads no banco com deduplicação por telefone, nome ou Instagram.
    Retorna (saved, skipped).
    """
    saved = skipped = 0

    for item in leads:
        norm_p = item.get('normalized_phone')
        inst = item.get('instagram')
        name = (item.get('name') or '').strip()

        if not name:
            skipped += 1
            continue

        if not norm_p and item.get('phone_number'):
            norm_p = _normalize_phone_local(item['phone_number'])

        website = item.get('website')
        website_type = item.get('website_detected_type')
        if website and not website_type:
            website_type = detect_website_type(website)

        dup = (
            (norm_p and Lead.objects.filter(user=user, normalized_phone=norm_p).exists())
            or Lead.objects.filter(user=user, name__iexact=name).exists()
            or (inst and Lead.objects.filter(user=user, instagram__iexact=inst, name__iexact=name).exists())
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
            source=item.get('source', 'google_maps'),
            status=item.get('status', 'novo'),
            is_verified=item.get('is_verified', False),
            price_range=item.get('_price_range') or item.get('price_range'),
            plus_code=item.get('_plus_code') or item.get('plus_code'),
            amenities=item.get('_amenities') or item.get('amenities') or None,
            total_photos=item.get('_total_photos') or item.get('total_photos'),
        )
        saved += 1

    return saved, skipped


def _normalize_phone_local(phone: str) -> str | None:
    import re
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