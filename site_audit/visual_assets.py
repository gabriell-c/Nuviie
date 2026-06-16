"""Gera crops AVIF a partir do JSON bruto do PageSpeed Insights (TTL 24h)."""

from __future__ import annotations

import base64
import io
import logging
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageDraw

from .models import SiteAuditVisualAsset

logger = logging.getLogger(__name__)

VISUAL_TTL_HOURS = 24
MAX_ELEMENTS_PER_AUDIT = 5
AVIF_QUALITY = 45


def _media_root() -> Path:
    return Path(settings.MEDIA_ROOT) / 'site_audit'


def _decode_screenshot_data(data: str) -> Image.Image | None:
    if not data:
        return None
    try:
        if data.startswith('data:'):
            _, b64 = data.split(',', 1)
        else:
            b64 = data
        raw = base64.b64decode(b64)
        return Image.open(io.BytesIO(raw)).convert('RGB')
    except Exception as exc:
        logger.warning('[SiteAuditVisual] decode screenshot: %s', exc)
        return None


def _get_full_page_image(lh: dict) -> tuple[Image.Image | None, dict | None]:
    fps = lh.get('fullPageScreenshot') or {}
    screenshot = fps.get('screenshot') or {}
    data = screenshot.get('data')
    img = _decode_screenshot_data(data)
    return img, fps


def _get_final_screenshot(audits: dict) -> Image.Image | None:
    audit = audits.get('final-screenshot') or {}
    details = audit.get('details') or {}
    return _decode_screenshot_data(details.get('data'))


def _save_avif(img: Image.Image, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        img.save(dest, format='AVIF', quality=AVIF_QUALITY)
        return True
    except Exception:
        try:
            img.save(dest.with_suffix('.webp'), format='WEBP', quality=80)
            return True
        except Exception as exc:
            logger.warning('[SiteAuditVisual] save image: %s', exc)
            return False


def _crop_rect(img: Image.Image, rect: dict, fps_meta: dict | None) -> Image.Image | None:
    if not rect:
        return None
    try:
        left = int(rect.get('left', 0))
        top = int(rect.get('top', 0))
        width = int(rect.get('width', 0))
        height = int(rect.get('height', 0))
        if width <= 0 or height <= 0:
            return None

        if fps_meta:
            scale = float(fps_meta.get('screenshot', {}).get('width', img.width)) / max(img.width, 1)
            if scale and abs(scale - 1.0) > 0.01:
                left = int(left / scale)
                top = int(top / scale)
                width = int(width / scale)
                height = int(height / scale)

        left = max(0, min(left, img.width - 1))
        top = max(0, min(top, img.height - 1))
        right = min(img.width, left + width)
        bottom = min(img.height, top + height)
        if right <= left or bottom <= top:
            return None
        return img.crop((left, top, right, bottom))
    except Exception as exc:
        logger.warning('[SiteAuditVisual] crop: %s', exc)
        return None


def _draw_highlight(img: Image.Image, rect: dict) -> Image.Image:
    out = img.copy()
    if not rect:
        return out
    try:
        draw = ImageDraw.Draw(out, 'RGBA')
        left = int(rect.get('left', 0))
        top = int(rect.get('top', 0))
        width = int(rect.get('width', 0))
        height = int(rect.get('height', 0))
        draw.rectangle(
            [left, top, left + width, top + height],
            outline=(239, 68, 68, 220),
            width=3,
        )
        draw.rectangle(
            [left, top, left + width, top + height],
            fill=(239, 68, 68, 60),
        )
    except Exception:
        pass
    return out


def _create_asset(
    report_id: int,
    img: Image.Image,
    *,
    kind: str,
    audit_id: str,
    strategy: str,
    element_index: int | None = None,
) -> str | None:
    asset_uuid = uuid.uuid4().hex[:12]
    rel_dir = f'site_audit/{report_id}'
    filename = f'{asset_uuid}.avif'
    dest = _media_root() / str(report_id) / f'{asset_uuid}.avif'
    if not _save_avif(img, dest):
        return None

    actual_name = dest.name
    if not dest.exists():
        webp = dest.with_suffix('.webp')
        if webp.exists():
            actual_name = webp.name
            filename = webp.name

    expires = timezone.now() + timedelta(hours=VISUAL_TTL_HOURS)
    rel_path = f'{rel_dir}/{actual_name}'
    SiteAuditVisualAsset.objects.create(
        report_id=report_id,
        asset_id=asset_uuid,
        file=rel_path,
        kind=kind,
        audit_id=audit_id,
        strategy=strategy,
        element_index=element_index,
        expires_at=expires,
    )
    return asset_uuid


def process_strategy_visuals(
    report_id: int,
    strategy: str,
    raw_data: dict,
    recommendations: dict,
) -> dict:
    """Cria assets visuais e retorna recommendations enriquecidas com visual_url."""
    lh = raw_data.get('lighthouseResult') or {}
    audits = lh.get('audits') or {}
    full_img, fps_meta = _get_full_page_image(lh)
    fallback_img = _get_final_screenshot(audits)

    base_img = full_img or fallback_img
    if not base_img:
        return recommendations

    recs = recommendations.get(strategy) or {}
    updated = {}
    for cat, issues in recs.items():
        new_issues = []
        for issue in issues:
            issue = dict(issue)
            elements = list(issue.get('elements') or [])
            if not elements:
                new_issues.append(issue)
                continue
            new_elements = []
            for idx, el in enumerate(elements[:MAX_ELEMENTS_PER_AUDIT]):
                el = dict(el)
                rect = el.pop('bounding_rect', None) or el.pop('boundingRect', None)
                crop = None
                if base_img and rect:
                    crop = _crop_rect(base_img, rect, fps_meta if full_img else None)
                if crop is None and fallback_img and rect:
                    highlighted = _draw_highlight(fallback_img, rect)
                    crop = highlighted
                elif crop is None and base_img:
                    crop = base_img.copy()
                    crop.thumbnail((400, 300))
                if crop:
                    asset_id = _create_asset(
                        report_id,
                        crop,
                        kind='crop' if rect else 'screenshot',
                        audit_id=issue.get('id', ''),
                        strategy=strategy,
                        element_index=idx,
                    )
                    if asset_id:
                        el['visual_url'] = f'/api/site-audits/{report_id}/visual/{asset_id}/'
                new_elements.append(el)
            issue['elements'] = new_elements
            new_issues.append(issue)
        updated[cat] = new_issues
    return updated


def merge_visual_recommendations(full_recs: dict, mobile_raw: dict, desktop_raw: dict, report_id: int) -> dict:
    out = dict(full_recs)
    out['mobile'] = process_strategy_visuals(report_id, 'mobile', mobile_raw, full_recs)
    out['desktop'] = process_strategy_visuals(report_id, 'desktop', desktop_raw, full_recs)
    return out
