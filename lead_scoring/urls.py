from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'api/scoring-rules', views.ScoringRuleViewSet, basename='scoring-rule')

urlpatterns = [
    path('regras-pontuacao/', views.scoring_rules_view, name='lead_scoring'),
    path('api/scoring-fields/', views.ScoringFieldsView.as_view(), name='scoring-fields'),
    path('', include(router.urls)),
]
