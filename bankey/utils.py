"""Utility functions for banking application."""
import random
import string
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
from .models import OTPVerification, AuditLog, LoginAttempt, FraudAlert
from decimal import Decimal


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def get_user_agent(request):
    """Get user agent from request."""
    return request.META.get('HTTP_USER_AGENT', '')[:500]


def generate_otp(length=6):
    """Generate random OTP code."""
    return ''.join(random.choices(string.digits, k=length))


def send_otp(user, purpose, send_to=None):
    """Generate and send OTP to user email."""
    otp_code = generate_otp()
    expires_at = timezone.now() + timedelta(minutes=10)
    
    # Save OTP to database
    otp = OTPVerification.objects.create(
        user=user,
        otp_code=otp_code,
        purpose=purpose,
        expires_at=expires_at
    )
    
    # Send email
    email = send_to or user.email
    subject = f"Kode OTP Verifikasi - {purpose}"
    
    message = f"""
    Halo {user.first_name or user.username},
    
    Kode OTP Anda adalah: {otp_code}
    
    Kode ini berlaku selama 10 menit.
    
    Jangan berikan kode ini kepada siapapun.
    
    Terima kasih,
    Tim Bank
    """
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
        return otp
    except Exception as e:
        print(f"Error sending OTP: {e}")
        return otp


def verify_otp(user, otp_code, purpose):
    """Verify OTP code."""
    otp = OTPVerification.objects.filter(
        user=user,
        otp_code=otp_code,
        purpose=purpose
    ).first()
    
    if not otp:
        return False, "Kode OTP tidak valid"
    
    if not otp.is_valid():
        return False, "Kode OTP sudah expired"
    
    otp.is_used = True
    otp.save()
    return True, "OTP berhasil diverifikasi"


def log_audit(user, action, request=None, description="", status="success"):
    """Log user activity for audit trail."""
    ip_address = get_client_ip(request) if request else None
    user_agent = get_user_agent(request) if request else ""
    
    AuditLog.objects.create(
        user=user,
        action=action,
        description=description,
        ip_address=ip_address,
        user_agent=user_agent,
        status=status
    )


def check_rate_limit(identifier, max_attempts=5, time_window_minutes=15):
    """Check if user has exceeded rate limit for login attempts."""
    time_threshold = timezone.now() - timedelta(minutes=time_window_minutes)
    
    recent_attempts = LoginAttempt.objects.filter(
        identifier=identifier,
        created_at__gte=time_threshold
    ).count()
    
    return recent_attempts >= max_attempts, recent_attempts


def record_login_attempt(identifier, is_successful, ip_address):
    """Record a login attempt."""
    LoginAttempt.objects.create(
        identifier=identifier,
        is_successful=is_successful,
        ip_address=ip_address
    )


def check_fraud(user, transaction_type, amount):
    """Check for suspicious activity patterns."""
    alerts = []
    
    # Check for unusually large transfer
    if transaction_type == 'transfer_out':
        user_avg_transfer = user.bank_account.transactions.filter(
            transaction_type='transfer_out'
        ).count()
        
        if user_avg_transfer > 0:
            avg_amount = sum(t.amount for t in user.bank_account.transactions.filter(
                transaction_type='transfer_out'
            )[:10]) / min(user_avg_transfer, 10)
            
            if amount > avg_amount * 5:  # More than 5x average
                alerts.append({
                    'type': 'unusual_amount',
                    'description': f'Transfer amount ({amount}) significantly higher than user average'
                })
    
    # Check for rapid consecutive transfers
    from django.db.models import Count
    recent_transfers = user.bank_account.transactions.filter(
        transaction_type__in=['transfer_out', 'transfer_in'],
        created_at__gte=timezone.now() - timedelta(minutes=30)
    ).count()
    
    if recent_transfers > 5:
        alerts.append({
            'type': 'rapid_transfers',
            'description': f'User made {recent_transfers} transfers in last 30 minutes'
        })
    
    # Create fraud alerts if any detected
    for alert in alerts:
        FraudAlert.objects.create(
            user=user,
            alert_type=alert['type'],
            description=alert['description']
        )
    
    return len(alerts) > 0, alerts


def send_email_notification(user, subject, message):
    """Send email notification to user."""
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def format_currency(amount):
    """Format amount as Indonesian currency."""
    return f"Rp {amount:,.0f}"


def create_notification(user, title, message, notif_type='system'):
    """Create a notification for user."""
    from .models import Notification
    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notif_type=notif_type
    )


def export_transactions_csv(transactions):
    """Export transactions to CSV format."""
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['Tanggal', 'Jenis', 'Jumlah', 'Saldo Akhir', 'Keterangan'])
    
    for tx in transactions:
        writer.writerow([
            tx.created_at.strftime('%d/%m/%Y %H:%M'),
            tx.get_transaction_type_display(),
            f"Rp {tx.amount:,.0f}",
            f"Rp {tx.balance_after:,.0f}",
            tx.description
        ])
    
    return output.getvalue()


def export_transactions_pdf(transactions, user):
    """Export transactions to PDF format."""
    from datetime import datetime
    
    content = f"""
    LAPORAN MUTASI REKENING
    =======================
    
    Nama: {user.first_name or user.username}
    Rekening: {user.bank_account.account_number if hasattr(user, 'bank_account') else '-'}
    Tanggal Cetak: {datetime.now().strftime('%d/%m/%Y %H:%M')}
    
    DETAIL TRANSAKSI:
    -----------------
    """
    
    for tx in transactions:
        content += f"\n{tx.created_at.strftime('%d/%m/%Y %H:%M')} | {tx.get_transaction_type_display():20} | Rp {tx.amount:>15,.0f} | Rp {tx.balance_after:>15,.0f} | {tx.description[:30]}"
    
    return content
