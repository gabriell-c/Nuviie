"""Notificações de prazo de projeto."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone

from leads.models import Lead
from notifications.models import Notification

User = get_user_model()


def _notify_all_users(title, message, level, lead, dedupe_key, trigger_date):
    for user in User.objects.filter(is_active=True):
        if Notification.objects.filter(user=user, dedupe_key=dedupe_key).exists():
            continue
        Notification.objects.create(
            user=user,
            title=title,
            message=message,
            level=level,
            lead=lead,
            trigger_date=trigger_date,
            dedupe_key=dedupe_key,
        )


def check_deadline_notifications() -> int:
    today = timezone.localdate()
    count = 0
    leads = Lead.objects.filter(
        status='fechado',
        project_deadline__isnull=False,
    ).select_related('contract')

    for lead in leads:
        days = lead.days_until_deadline()
        if days is None:
            continue
        dl = lead.project_deadline

        if days < 0:
            key = f'deadline_overdue_{lead.id}_{dl}'
            _notify_all_users(
                f'Prazo vencido — {lead.name}',
                f'O prazo do projeto venceu em {dl.strftime("%d/%m/%Y")}.',
                'danger', lead, key, dl,
            )
            count += 1
        elif days == 0:
            key = f'deadline_today_{lead.id}_{dl}'
            _notify_all_users(
                f'Prazo hoje — {lead.name}',
                f'O prazo do projeto é hoje ({dl.strftime("%d/%m/%Y")}).',
                'danger', lead, key, dl,
            )
            count += 1
        elif days <= 2:
            key = f'deadline_2d_{lead.id}_{dl}'
            _notify_all_users(
                f'Prazo crítico — {lead.name}',
                f'Faltam {days} dia(s) para o prazo ({dl.strftime("%d/%m/%Y")}).',
                'danger', lead, key, dl,
            )
            count += 1
        elif days <= 4:
            key = f'deadline_4d_{lead.id}_{dl}'
            _notify_all_users(
                f'Prazo se aproximando — {lead.name}',
                f'Faltam {days} dias para o prazo ({dl.strftime("%d/%m/%Y")}).',
                'warning', lead, key, dl,
            )
            count += 1
    return count
