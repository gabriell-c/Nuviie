"""Recálculo em massa de pontuações."""

from django.db import transaction


def recalculate_all_leads() -> int:
    """Recalcula quality_score e score_breakdown de todos os leads."""
    from leads.models import Lead

    from .engine import calculate_score

    count = 0
    with transaction.atomic():
        for lead in Lead.objects.iterator(chunk_size=200):
            result = calculate_score(lead)
            Lead.objects.filter(pk=lead.pk).update(
                quality_score=result['total'],
                score_breakdown=result,
            )
            count += 1
    return count
