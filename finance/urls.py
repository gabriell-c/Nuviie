from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import FinanceCategoryViewSet, FinanceEntryViewSet, finance_dashboard_view

router = DefaultRouter()
router.register(r'categories', FinanceCategoryViewSet, basename='finance-category')
router.register(r'entries', FinanceEntryViewSet, basename='finance-entry')

urlpatterns = [
    path('financeiro/', finance_dashboard_view, name='finance_dashboard'),
    path('api/finance/', include(router.urls)),
]
