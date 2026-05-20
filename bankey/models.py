from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.hashers import make_password, check_password
import random
import string


class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('teller', 'Teller (Kasir)'),
        ('cs', 'Customer Service'),
        ('nasabah', 'Nasabah'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='nasabah')
    phone = models.CharField(max_length=20, blank=True, null=True)
    pin_hash = models.CharField(max_length=256, blank=True, null=True)
    daily_limit = models.DecimalField(max_digits=15, decimal_places=2, default=50000000.00)
    account_locked = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    def set_pin(self, raw_pin):
        self.pin_hash = make_password(raw_pin)
        self.save()

    def check_pin(self, raw_pin):
        if self.pin_hash:
            return check_password(raw_pin, self.pin_hash)
        return False

    def has_pin(self):
        return bool(self.pin_hash)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Auto-create UserProfile when a new User is created."""
    if created:
        role = 'admin' if instance.is_superuser else 'nasabah'
        UserProfile.objects.get_or_create(user=instance, defaults={'role': role})


class BankAccount(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='bank_account')
    account_number = models.CharField(max_length=16, unique=True)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=1000000.00)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.account_number} - {self.user.first_name}"

    @staticmethod
    def generate_account_number():
        while True:
            number = ''.join(random.choices(string.digits, k=10))
            if not BankAccount.objects.filter(account_number=number).exists():
                return number


@receiver(post_save, sender=User)
def create_bank_account(sender, instance, created, **kwargs):
    """Auto-create BankAccount for non-superuser when a new User is created."""
    if created and not instance.is_superuser:
        BankAccount.objects.get_or_create(
            user=instance,
            defaults={'account_number': BankAccount.generate_account_number()}
        )


class Transaction(models.Model):
    TYPE_CHOICES = (
        ('credit', 'Setor Tunai'),
        ('debit', 'Tarik Tunai'),
        ('transfer_in', 'Transfer Masuk'),
        ('transfer_out', 'Transfer Keluar'),
        ('bill', 'Pembayaran Tagihan'),
    )
    account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=15, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    related_account = models.CharField(max_length=16, blank=True, null=True)
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.account.account_number} - {self.transaction_type} - {self.amount}"


class Queue(models.Model):
    TYPES = (
        ('CS', 'Customer Service'),
        ('K', 'Kasir'),
    )
    STATUSES = (
        ('waiting', 'Menunggu'),
        ('calling', 'Sedang Dipanggil'),
        ('done', 'Selesai'),
    )
    number = models.CharField(max_length=10)
    queue_type = models.CharField(max_length=2, choices=TYPES)
    status = models.CharField(max_length=10, choices=STATUSES, default='waiting')
    counter = models.IntegerField(null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='queues')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.queue_type}-{self.number}"


class SupportTicket(models.Model):
    STATUS_CHOICES = (
        ('open', 'Menunggu'),
        ('in_progress', 'Diproses'),
        ('closed', 'Selesai'),
    )
    CATEGORY_CHOICES = (
        ('transfer', 'Transfer & Pembayaran'),
        ('account', 'Akun & Keamanan'),
        ('card', 'Kartu & ATM'),
        ('loan', 'Pinjaman & Kredit'),
        ('other', 'Lainnya'),
    )
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='other')
    detail = models.TextField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.category}"


class TicketReply(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='replies')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    is_staff_reply = models.BooleanField(default=False)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Reply #{self.id} on Ticket #{self.ticket_id}"


class Notification(models.Model):
    TYPES = (
        ('transfer', 'Transfer'),
        ('ticket', 'Tiket'),
        ('system', 'Sistem'),
        ('bill', 'Tagihan'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=100)
    message = models.CharField(max_length=400)
    notif_type = models.CharField(max_length=10, choices=TYPES, default='system')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.title}"


# ==================== NEW FEATURES ====================

class AuditLog(models.Model):
    """Track all sensitive activities for compliance & security."""
    ACTION_TYPES = (
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('transfer', 'Transfer Dana'),
        ('profile_update', 'Update Profil'),
        ('kyc_submit', 'Submit KYC'),
        ('password_change', 'Ubah Password'),
        ('pin_change', 'Ubah PIN'),
        ('failed_login', 'Gagal Login'),
        ('recipient_add', 'Tambah Penerima'),
        ('scheduled_tx', 'Transfer Terjadwal'),
    )
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, default='success', choices=[('success', 'Success'), ('failed', 'Failed')])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', '-created_at'])]

    def __str__(self):
        return f"{self.user.username if self.user else 'System'} - {self.action} ({self.created_at})"


class OTPVerification(models.Model):
    """OTP for transaction verification & password reset."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otp_verifications')
    otp_code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=[
        ('transfer', 'Verifikasi Transfer'),
        ('password_reset', 'Reset Password'),
        ('profile_update', 'Update Profil'),
    ])
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"OTP {self.user.username} - {self.purpose}"

    def is_valid(self):
        from django.utils import timezone
        return not self.is_used and timezone.now() < self.expires_at


class KYCVerification(models.Model):
    """Know Your Customer - User identity verification."""
    VERIFICATION_STATUS = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('under_review', 'Under Review'),
    )
    DOCUMENT_TYPES = (
        ('ktp', 'KTP'),
        ('npwp', 'NPWP'),
        ('passport', 'Passport'),
        ('sim', 'SIM'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='kyc_verification')
    
    # Personal Info
    full_name = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=50, blank=True)
    province = models.CharField(max_length=50, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)
    
    # Document Info
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES, blank=True)
    document_number = models.CharField(max_length=50, blank=True, unique=True, null=True)
    document_image_url = models.CharField(max_length=500, blank=True)
    selfie_image_url = models.CharField(max_length=500, blank=True)
    
    # Status
    status = models.CharField(max_length=15, choices=VERIFICATION_STATUS, default='pending')
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"KYC {self.user.username} - {self.get_status_display()}"


class Recipient(models.Model):
    """Saved payees for quick transfers."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recipients')
    account_number = models.CharField(max_length=16)
    recipient_name = models.CharField(max_length=100)
    bank_name = models.CharField(max_length=50, default="Bank Indonesia")
    is_favorite = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'account_number')
        ordering = ['-is_favorite', '-created_at']

    def __str__(self):
        return f"{self.user.username} -> {self.recipient_name} ({self.account_number})"


class TransactionFee(models.Model):
    """Fee management for different transaction types."""
    TRANSACTION_TYPES = (
        ('transfer_internal', 'Transfer Internal (Antar Cabang)'),
        ('transfer_external', 'Transfer Eksternal (Antar Bank)'),
        ('bill_payment', 'Pembayaran Tagihan'),
        ('withdrawal', 'Penarikan Tunai'),
        ('cash_deposit', 'Setoran Tunai'),
    )
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_TYPES, unique=True)
    fee_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    flat_fee = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    min_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    max_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def calculate_fee(self, amount):
        """Calculate total fee for given amount."""
        if self.max_amount and amount > self.max_amount:
            return None  # Transaction exceeds limit
        fee = self.flat_fee + (amount * self.fee_percentage / 100)
        return fee

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.fee_percentage}% + Rp {self.flat_fee}"


class LoginAttempt(models.Model):
    """Track login attempts for rate limiting & fraud detection."""
    identifier = models.CharField(max_length=255)  # username or IP
    attempt_type = models.CharField(max_length=20, default='login')
    is_successful = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['identifier', '-created_at'])]

    def __str__(self):
        return f"{self.identifier} - {self.attempt_type}"


class ScheduledTransaction(models.Model):
    """Recurring/scheduled transfers."""
    FREQUENCY_CHOICES = (
        ('once', 'Sekali'),
        ('daily', 'Harian'),
        ('weekly', 'Mingguan'),
        ('monthly', 'Bulanan'),
        ('yearly', 'Tahunan'),
    )
    STATUS_CHOICES = (
        ('active', 'Aktif'),
        ('paused', 'Dijeda'),
        ('completed', 'Selesai'),
        ('cancelled', 'Dibatalkan'),
    )
    
    account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='scheduled_transactions')
    recipient_account = models.CharField(max_length=16)
    recipient_name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default='monthly')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='active')
    
    start_date = models.DateField()
    next_execution = models.DateTimeField()
    end_date = models.DateField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.account.account_number} -> {self.recipient_name} ({self.frequency})"


class UserNotificationPreference(models.Model):
    """User preferences for notifications."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_preference')
    
    email_on_transfer = models.BooleanField(default=True)
    email_on_login = models.BooleanField(default=False)
    email_on_kyc = models.BooleanField(default=True)
    email_daily_summary = models.BooleanField(default=False)
    
    sms_on_large_transfer = models.BooleanField(default=True)
    sms_threshold = models.DecimalField(max_digits=15, decimal_places=2, default=5000000)
    
    push_notifications = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notification Preference - {self.user.username}"


class FraudAlert(models.Model):
    """Track suspicious activities."""
    ALERT_TYPES = (
        ('unusual_amount', 'Unusual Transaction Amount'),
        ('rapid_transfers', 'Multiple Rapid Transfers'),
        ('location_change', 'Location Change'),
        ('failed_login_attempts', 'Multiple Failed Login Attempts'),
        ('profile_access_unusual', 'Unusual Profile Access'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='fraud_alerts')
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    description = models.TextField()
    is_resolved = models.BooleanField(default=False)
    action_taken = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Alert {self.user.username} - {self.get_alert_type_display()}"
