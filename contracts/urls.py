from django.urls import path
from . import views

urlpatterns = [
    path('templates/', views.template_list_view, name='template_list'),
    path('templates/<int:template_id>/fill/', views.fill_template_view, name='fill_template'),
    path('templates/<int:template_id>/delete/', views.delete_template_view, name='delete_template'),
    path('history/', views.contracts_history_view, name='contracts_history'),
    path('history/<int:contract_id>/download/', views.download_contract_view, name='download_contract'),
    path('history/<int:contract_id>/delete/', views.delete_contract_view, name='delete_contract'),
]
