"""Serviço central de auditoria."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from .models import ActivityLog

User = get_user_model()


def log_activity(
    action: str,
    description: str,
    *,
    user=None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    metadata: dict | None = None,
    request=None,
) -> ActivityLog:
    ip = None
    if request:
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            ip = xff.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')

    return ActivityLog.objects.create(
        user=user,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        description=description,
        metadata=metadata or {},
        ip_address=ip,
    )
