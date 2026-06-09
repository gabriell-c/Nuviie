from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('password-reset/', views.password_reset_request_view, name='password_reset_request'),
    path('password-reset/verify/', views.password_reset_verify_view, name='password_reset_verify'),
    path('profile/', views.profile_view, name='profile'),
    path('face-register/', views.face_register_view, name='face_register'),
    path('face-login/', views.face_login_view, name='face_login'),
    path('face-toggle/', views.face_toggle_view, name='face_toggle'),
    ]
