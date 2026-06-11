from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'api/prompt-categories', views.PromptCategoryViewSet, basename='prompt-category')
router.register(r'api/prompts', views.PromptViewSet, basename='prompt')

urlpatterns = [
    path('biblioteca-prompts/', views.prompt_library_view, name='prompt_library'),
    path('', include(router.urls)),
]
