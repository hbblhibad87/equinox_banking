from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='root_login'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('dashboard/admin/', views.dashboard_admin_view, name='dashboard_admin'),
    path('dashboard/teller/', views.dashboard_teller_view, name='dashboard_teller'),
    path('dashboard/cs/', views.dashboard_cs_view, name='dashboard_cs'),
    path('dashboard/nasabah/', views.dashboard_nasabah_view, name='dashboard_nasabah'),
    path('nasabah/mutasi/', views.mutasi_view, name='mutasi'),
    path('nasabah/transfer/', views.transfer_view, name='transfer'),
    path('nasabah/transfer/verify/', views.transfer_verify, name='transfer_verify'),
    path('nasabah/tiket/', views.tiket_view, name='tiket'),
    path('support/', views.support_view, name='support'),
    path('logout/', views.logout_view, name='logout'),
    
    # New features
    path('profile/kyc/', views.kyc_profile_view, name='kyc_profile'),
    path('recipients/', views.recipients_view, name='recipients'),
    path('scheduled-transfer/', views.scheduled_transfer_view, name='scheduled_transfer'),
    path('statement/export/', views.statement_export_view, name='statement_export'),
    path('notifications/preference/', views.notification_preference_view, name='notification_preference'),
    path('fraud-alerts/', views.fraud_alerts_view, name='fraud_alerts'),
    path('audit-log/', views.audit_log_view, name='audit_log'),
    
    # Admin features
    path('admin/analytics/', views.admin_analytics_view, name='admin_analytics'),
    path('admin/kyc-review/', views.admin_kyc_review_view, name='admin_kyc_review'),
    path('admin/fraud-management/', views.admin_fraud_management_view, name='admin_fraud_management'),
    
    # API endpoints
    path('api/dashboard-data/', views.api_dashboard_data, name='api_dashboard_data'),
    path('api/take-queue/', views.api_take_queue, name='api_take_queue'),
    path('api/call-queue/', views.api_call_queue, name='api_call_queue'),
]
