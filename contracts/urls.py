from django.urls import path
from . import views

urlpatterns = [
    path('', views.generate_view, name='template_list'),
    path('templates/', views.generate_view, name='contract_templates'),
    path('generate/', views.generate_view, name='contract_generate'),
    path('history/', views.contracts_history_view, name='contracts_history'),
    path('history/<int:contract_id>/download/', views.download_contract_view, name='download_contract'),
    path('history/<int:contract_id>/delete/', views.delete_contract_view, name='delete_contract'),
]
