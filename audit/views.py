from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render

from .models import ActivityLog


@login_required
def history_view(request):
    qs = ActivityLog.objects.select_related('user').all()

    action = request.GET.get('action', '').strip()
    search = request.GET.get('search', '').strip()

    if action:
        qs = qs.filter(action=action)
    if search:
        qs = qs.filter(
            Q(description__icontains=search)
            | Q(user__username__icontains=search)
            | Q(user__email__icontains=search)
        )

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'audit/history.html', {
        'current_page': 'audit_history',
        'logs': page,
        'action_choices': ActivityLog.ACTION_CHOICES,
        'selected_action': action,
        'search': search,
    })
