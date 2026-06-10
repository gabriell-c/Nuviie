from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .services import log_activity


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    log_activity(
        'login',
        f'{user.get_full_name() or user.username} fez login.',
        user=user,
        entity_type='user',
        entity_id=user.pk,
        request=request,
    )


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    if user:
        log_activity(
            'logout',
            f'{user.get_full_name() or user.username} saiu do sistema.',
            user=user,
            entity_type='user',
            entity_id=user.pk,
            request=request,
        )
