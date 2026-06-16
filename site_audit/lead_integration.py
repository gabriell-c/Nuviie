"""Integração de auditorias com leads (export + serializer)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import SiteAuditReport
from .pagespeed import get_top_issues

if TYPE_CHECKING:
    from leads.models import Lead


def get_latest_completed_audit(lead: Lead) -> SiteAuditReport | None:
    return (
        SiteAuditReport.objects.filter(
            lead=lead,
            status=SiteAuditReport.STATUS_COMPLETED,
        )
        .order_by('-completed_at', '-created_at')
        .first()
    )


def build_site_audit_summary(lead: Lead) -> dict | None:
    audit = get_latest_completed_audit(lead)
    if not audit:
        return None
    return {
        'audit_id': audit.id,
        'url': audit.url,
        'scores': audit.scores,
        'core_web_vitals': audit.core_web_vitals,
        'top_issues': get_top_issues(audit.recommendations or {}, limit=5),
        'summary': audit.summary,
        'completed_at': audit.completed_at.isoformat() if audit.completed_at else None,
    }


def build_site_audit_export_section(lead: Lead) -> dict | None:
    audit = get_latest_completed_audit(lead)
    if not audit:
        return None

    recs = audit.recommendations or {}
    top_all = []
    for strategy in ('mobile', 'desktop'):
        s_recs = recs.get(strategy) or {}
        for cat in ('performance', 'seo', 'best_practices', 'accessibility'):
            for item in (s_recs.get(cat) or [])[:5]:
                top_all.append({
                    'strategy': strategy,
                    'category': cat,
                    'title': item.get('title'),
                    'description': (item.get('description') or '')[:400],
                    'display_value': item.get('display_value'),
                    'savings_ms': item.get('savings_ms'),
                    'severity': item.get('severity'),
                })
    top_all.sort(key=lambda x: 0 if x.get('severity') == 'high' else 1)
    top_all = top_all[:10]

    return {
        'url': audit.url,
        'audit_id': audit.id,
        'completed_at': audit.completed_at.isoformat() if audit.completed_at else None,
        'summary': audit.summary,
        'scores': audit.scores,
        'core_web_vitals': audit.core_web_vitals,
        'principais_melhorias': top_all,
    }
