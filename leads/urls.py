from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'api/leads', views.LeadViewSet, basename='api-lead')

urlpatterns = [
    # Dashboard and Scrapers HTML templates
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('kanban/', views.kanban_view, name='kanban'),
    path('scraper/maps/', views.maps_scraper_view, name='maps_scraper'),
    path('scraper/instagram/', views.instagram_scraper_view, name='instagram_scraper'),
    
    # Export Lead Data
    path('leads/export/', views.export_leads_view, name='export_leads'),

    # Browser Preview (Playwright screenshot)
    path('leads/preview/', views.browser_preview_view, name='browser_preview'),
    
    # ✅ NOVO: Abre Firefox real com a URL
    path('leads/open-browser/', views.open_browser_view, name='open_browser'),

    # DRF API urls
    path('', include(router.urls)),
]