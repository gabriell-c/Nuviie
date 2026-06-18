from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'instances', views.WhatsAppInstanceViewSet, basename='whatsapp-instance')
router.register(r'messages', views.WhatsAppMessageViewSet, basename='whatsapp-message')

urlpatterns = [
    path('whatsapp/', views.whatsapp_page, name='whatsapp'),
    path('api/whatsapp/webhook/', views.evolution_webhook, name='whatsapp_webhook'),
    path('api/whatsapp/', include(router.urls)),
]
