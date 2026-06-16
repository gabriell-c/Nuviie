from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import SiteAuditViewSet, site_audit_dashboard_view

router = DefaultRouter()
router.register(r'site-audits', SiteAuditViewSet, basename='site-audit')

urlpatterns = [
    path('auditoria-sites/', site_audit_dashboard_view, name='site_audit'),
    path('api/', include(router.urls)),
]
