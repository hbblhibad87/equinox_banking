from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='root_login'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('support/', views.support_view, name='support'),
    path('logout/', views.logout_view, name='logout'),
    path('api/dashboard-data/', views.api_dashboard_data, name='api_dashboard_data'),
    path('api/take-queue/', views.api_take_queue, name='api_take_queue'),
    path('api/call-queue/', views.api_call_queue, name='api_call_queue'),
]
