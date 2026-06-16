"""Exportação de relatórios de auditoria em MD/JSON."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import SiteAuditReport


def audit_to_dict(report: SiteAuditReport) -> dict:
    return {
        'id': report.id,
        'url': report.url,
        'status': report.status,
        'lead_id': report.lead_id,
        'lead_name': report.lead.name if report.lead_id else None,
        'scores': report.scores,
        'core_web_vitals': report.core_web_vitals,
        'recommendations': report.recommendations,
        'summary': report.summary,
        'created_at': report.created_at.isoformat() if report.created_at else None,
        'completed_at': report.completed_at.isoformat() if report.completed_at else None,
    }


def audit_to_json(report: SiteAuditReport, *, indent: int = 2) -> str:
    return json.dumps(audit_to_dict(report), ensure_ascii=False, indent=indent)


def audit_to_markdown(report: SiteAuditReport) -> str:
    lines = [
        f'# Auditoria de Site — {report.url}',
        '',
        f'**Status:** {report.get_status_display()}',
    ]
    if report.lead_id:
        lines.append(f'**Lead associado:** {report.lead.name} (ID {report.lead_id})')
    if report.summary:
        lines += ['', '## Resumo', '', report.summary, '']

    scores = report.scores or {}
    lines += ['## Notas Lighthouse', '']
    lines.append('| Categoria | Mobile | Desktop |')
    lines.append('|-----------|--------|---------|')
    for cat, label in [
        ('performance', 'Performance'),
        ('seo', 'SEO'),
        ('accessibility', 'Acessibilidade'),
        ('best_practices', 'Boas práticas'),
    ]:
        mob = (scores.get('mobile') or {}).get(cat, '—')
        desk = (scores.get('desktop') or {}).get(cat, '—')
        lines.append(f'| {label} | {mob} | {desk} |')
    lines.append('')

    cwv = report.core_web_vitals or {}
    for strategy in ('mobile', 'desktop'):
        data = cwv.get(strategy) or {}
        if not data:
            continue
        lines += [f'## Core Web Vitals ({strategy.capitalize()})', '']
        for key, item in data.items():
            lines.append(f'- **{key}:** {item.get("display", item.get("value"))}')
        lines.append('')

    recs = report.recommendations or {}
    cat_labels = {
        'performance': 'Performance',
        'seo': 'SEO',
        'accessibility': 'Acessibilidade',
        'best_practices': 'Boas práticas',
    }
    for strategy in ('mobile', 'desktop'):
        s_recs = recs.get(strategy) or {}
        for cat, label in cat_labels.items():
            items = s_recs.get(cat) or []
            if not items:
                continue
            lines += [f'## {label} — o que melhorar ({strategy.capitalize()})', '']
            for i, item in enumerate(items[:15], 1):
                lines.append(f'### {i}. {item.get("title", "Item")}')
                if item.get('display_value'):
                    lines.append(f'- **Valor:** {item["display_value"]}')
                if item.get('savings_ms'):
                    lines.append(f'- **Economia estimada:** {item["savings_ms"]} ms')
                desc = (item.get('description') or '').strip()
                if desc:
                    lines.append(f'- **Detalhe:** {desc[:500]}')
                lines.append('')
    return '\n'.join(lines)
