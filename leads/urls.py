from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'api/leads', views.LeadViewSet, basename='api-lead')

urlpatterns = [
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('kanban/', views.kanban_view, name='kanban'),
    path('scraper/instagram/', views.instagram_scraper_view, name='instagram_scraper'),
    path('leads/export/', views.export_leads_view, name='export_leads'),
    path('leads/import/', views.import_leads_view, name='import_leads'),
    path('api/leads/bulk-import/', views.bulk_import_leads_view, name='bulk_import_leads'),
    path('api/leads/existing-handles/', views.extension_existing_handles_view, name='extension_existing_handles'),
    path('', include(router.urls)),
]
