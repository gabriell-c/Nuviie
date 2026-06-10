from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from .services import collect_metrics


@login_required
def analytics_view(request):
    return render(request, 'monitoring/analytics.html', {
        'current_page': 'monitoring',
    })


@login_required
def analytics_api_view(request):
    return JsonResponse(collect_metrics())
