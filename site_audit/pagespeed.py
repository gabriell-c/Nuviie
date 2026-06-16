"""Cliente Google PageSpeed Insights v5 + parser Lighthouse."""

from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

PSI_URL = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed'

CATEGORY_MAP = {
    'performance': 'performance',
    'accessibility': 'accessibility',
    'best-practices': 'best_practices',
    'seo': 'seo',
}

CWV_AUDITS = {
    'largest-contentful-paint': 'lcp_ms',
    'cumulative-layout-shift': 'cls',
    'interaction-to-next-paint': 'inp_ms',
    'first-contentful-paint': 'fcp_ms',
    'server-response-time': 'ttfb_ms',
    'speed-index': 'speed_index_ms',
}

ISSUE_CATEGORIES = {
    'performance': 'performance',
    'accessibility': 'accessibility',
    'best-practices': 'best_practices',
    'seo': 'seo',
}


def _api_key() -> str:
    key = getattr(settings, 'GOOGLE_PAGESPEED_API_KEY', '') or ''
    if not key:
        raise ValueError(
            'GOOGLE_PAGESPEED_API_KEY não configurada. Adicione ao arquivo .env.'
        )
    return key


def _score_pct(category: dict | None) -> int | None:
    if not category:
        return None
    score = category.get('score')
    if score is None:
        return None
    return max(0, min(100, int(round(float(score) * 100))))


def _extract_table_elements(audit: dict) -> list[dict]:
    details = audit.get('details') or {}
    if details.get('type') != 'table':
        return []
    elements = []
    for item in (details.get('items') or [])[:5]:
        if not isinstance(item, dict):
            continue
        node = item.get('node') or {}
        rect = node.get('boundingRect')
        snippet = node.get('snippet') or ''
        selector = node.get('selector') or ''
        if not (snippet or selector or rect):
            continue
        explanation = (
            item.get('explanation')
            or item.get('failureSummary')
            or item.get('reason')
            or ''
        )
        elements.append({
            'snippet': snippet[:1200],
            'selector': selector[:500],
            'label': node.get('nodeLabel') or node.get('label') or '',
            'explanation': str(explanation)[:800],
            'bounding_rect': rect,
        })
    return elements


def _audit_issue(audit_id: str, audit: dict) -> dict | None:
    score = audit.get('score')
    if score is not None and score >= 0.99:
        return None

    details = audit.get('details') or {}
    detail_type = details.get('type', '')
    savings_ms = None
    savings_bytes = None
    if detail_type == 'opportunity':
        overall = details.get('overallSavingsMs')
        if overall is not None:
            savings_ms = int(overall)
        savings_bytes = details.get('overallSavingsBytes')

    numeric = audit.get('numericValue')
    display = audit.get('displayValue') or ''
    severity = 'high' if (score is not None and score < 0.5) else 'medium' if score is not None and score < 0.9 else 'low'

    return {
        'id': audit_id,
        'title': audit.get('title') or audit_id,
        'description': (audit.get('description') or '').replace('`', "'")[:800],
        'display_value': display,
        'numeric_value': numeric,
        'score': score,
        'severity': severity,
        'savings_ms': savings_ms,
        'savings_bytes': savings_bytes,
        'type': detail_type or 'diagnostic',
        'elements': _extract_table_elements(audit),
    }


def parse_lighthouse_result(data: dict) -> dict:
    """Converte resposta PSI em estrutura normalizada."""
    lh = data.get('lighthouseResult') or {}
    categories = lh.get('categories') or {}
    audits = lh.get('audits') or {}

    scores = {}
    for psi_key, our_key in CATEGORY_MAP.items():
        scores[our_key] = _score_pct(categories.get(psi_key))

    cwv = {}
    for audit_id, field in CWV_AUDITS.items():
        audit = audits.get(audit_id) or {}
        val = audit.get('numericValue')
        if val is not None:
            cwv[field] = {
                'value': val,
                'display': audit.get('displayValue') or str(val),
                'score': audit.get('score'),
            }

    recommendations: dict[str, list] = {
        'performance': [],
        'seo': [],
        'accessibility': [],
        'best_practices': [],
    }

    cat_audit_ids: dict[str, set[str]] = {}
    for psi_key, our_key in ISSUE_CATEGORIES.items():
        refs = (categories.get(psi_key) or {}).get('auditRefs') or []
        cat_audit_ids[our_key] = {r.get('id') for r in refs if r.get('id')}

    for audit_id, audit in audits.items():
        if not isinstance(audit, dict):
            continue
        ref = audit.get('scoreDisplayMode')
        if ref in ('notApplicable', 'manual', 'informative'):
            continue

        details = audit.get('details') or {}
        assigned = None
        for our_key, ids in cat_audit_ids.items():
            if audit_id in ids:
                assigned = our_key
                break
        if not assigned and details.get('type') == 'opportunity':
            assigned = 'performance'

        if assigned:
            issue = _audit_issue(audit_id, audit)
            if issue:
                recommendations[assigned].append(issue)

    for key in recommendations:
        recommendations[key].sort(
            key=lambda x: (
                0 if x.get('severity') == 'high' else 1 if x.get('severity') == 'medium' else 2,
                -(x.get('savings_ms') or 0),
            )
        )
        recommendations[key] = recommendations[key][:25]

    return {
        'scores': scores,
        'core_web_vitals': cwv,
        'recommendations': recommendations,
    }


def run_pagespeed(url: str, strategy: str = 'mobile') -> dict:
    """Executa uma análise PSI para mobile ou desktop."""
    _data, parsed = run_pagespeed_raw(url, strategy)
    return parsed


def run_pagespeed_raw(url: str, strategy: str = 'mobile') -> tuple[dict, dict]:
    """Executa PSI e retorna (json bruto, estrutura parseada)."""
    params = [
        ('url', url),
        ('strategy', strategy),
        ('key', _api_key()),
        ('locale', 'pt-BR'),
        ('category', 'performance'),
        ('category', 'accessibility'),
        ('category', 'best-practices'),
        ('category', 'seo'),
    ]
    resp = requests.get(PSI_URL, params=params, timeout=120)
    if resp.status_code != 200:
        try:
            err = resp.json()
            msg = err.get('error', {}).get('message') or resp.text[:300]
        except Exception:
            msg = resp.text[:300]
        raise ValueError(f'PageSpeed API erro {resp.status_code}: {msg}')

    data = resp.json()
    return data, parse_lighthouse_result(data)


def run_full_audit(url: str, report_id: int | None = None) -> dict:
    """Executa mobile + desktop e retorna payload consolidado."""
    mobile_raw, mobile = run_pagespeed_raw(url, 'mobile')
    desktop_raw, desktop = run_pagespeed_raw(url, 'desktop')

    scores = {
        'mobile': mobile['scores'],
        'desktop': desktop['scores'],
    }
    core_web_vitals = {
        'mobile': mobile['core_web_vitals'],
        'desktop': desktop['core_web_vitals'],
    }
    recommendations = {
        'mobile': mobile['recommendations'],
        'desktop': desktop['recommendations'],
    }

    if report_id is not None:
        from .visual_assets import merge_visual_recommendations
        recommendations = merge_visual_recommendations(
            recommendations, mobile_raw, desktop_raw, report_id,
        )

    summary = build_summary(url, scores, core_web_vitals, recommendations)
    return {
        'scores': scores,
        'core_web_vitals': core_web_vitals,
        'recommendations': recommendations,
        'summary': summary,
    }


def _fmt_cwv_label(field: str, display: str) -> str:
    labels = {
        'lcp_ms': 'LCP',
        'cls': 'CLS',
        'inp_ms': 'INP',
        'fcp_ms': 'FCP',
        'ttfb_ms': 'TTFB',
        'speed_index_ms': 'Speed Index',
    }
    return f'{labels.get(field, field)} {display}'


def build_summary(
    url: str,
    scores: dict,
    cwv: dict,
    recommendations: dict,
) -> str:
    parts = [f'Auditoria: {url}']
    for strategy in ('mobile', 'desktop'):
        s = scores.get(strategy) or {}
        perf = s.get('performance')
        seo = s.get('seo')
        line = f'{strategy.capitalize()}: Performance {perf}/100, SEO {seo}/100'
        m_cwv = cwv.get(strategy) or {}
        lcp = m_cwv.get('lcp_ms')
        if lcp:
            line += f' — {_fmt_cwv_label("lcp_ms", lcp.get("display", ""))}'
        parts.append(line)

        recs = recommendations.get(strategy) or {}
        perf_issues = recs.get('performance') or []
        seo_issues = recs.get('seo') or []
        if perf_issues:
            top = perf_issues[0].get('title', '')
            parts.append(f'  Performance ({strategy}): {len(perf_issues)} oportunidade(s). Principal: {top}')
        if seo_issues:
            top = seo_issues[0].get('title', '')
            parts.append(f'  SEO ({strategy}): {len(seo_issues)} problema(s). Principal: {top}')

    return '\n'.join(parts)


def get_top_issues(recommendations: dict, *, limit: int = 3) -> list[dict]:
    """Top issues across mobile (priority) for lead summary."""
    issues = []
    mobile = recommendations.get('mobile') or {}
    for cat in ('performance', 'seo', 'best_practices', 'accessibility'):
        for item in (mobile.get(cat) or [])[:limit]:
            issues.append({**item, 'category': cat, 'strategy': 'mobile'})
            if len(issues) >= limit:
                return issues
    return issues[:limit]
