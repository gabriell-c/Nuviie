from django.urls import path
from . import views

urlpatterns = [
    path('chat/', views.chat_home, name='chat'),
    path('chat/new/', views.new_conversation, name='chat_new'),
    path('chat/list/', views.list_conversations, name='chat_list'),
    path('chat/<int:conv_id>/messages/', views.load_messages, name='chat_messages'),
    path('chat/<int:conv_id>/delete/', views.delete_conversation, name='chat_delete'),
    path('chat/send/', views.send_message, name='chat_send'),
]
