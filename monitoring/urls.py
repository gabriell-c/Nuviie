from django.urls import path
from . import views

urlpatterns = [
    path('analytics/', views.analytics_view, name='monitoring_analytics'),
    path('api/metrics/', views.analytics_api_view, name='monitoring_api'),
]
