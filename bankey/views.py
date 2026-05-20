from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Sum, Count
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from datetime import timedelta, datetime
from .models import (
    Queue, SupportTicket, UserProfile, BankAccount, Transaction, 
    AuditLog, OTPVerification, KYCVerification, Recipient, TransactionFee,
    LoginAttempt, ScheduledTransaction, UserNotificationPreference, FraudAlert,
    Notification, TicketReply
)
from .utils import (
    get_client_ip, get_user_agent, send_otp, verify_otp, log_audit,
    check_rate_limit, record_login_attempt, check_fraud, send_email_notification,
    format_currency, create_notification, export_transactions_csv, export_transactions_pdf
)
import json


def get_user_role(user):
    """Helper: get user role from profile, default 'nasabah'."""
    try:
        return user.profile.role
    except UserProfile.DoesNotExist:
        # Auto-create profile if missing
        profile = UserProfile.objects.create(
            user=user,
            role='admin' if user.is_superuser else 'nasabah'
        )
        return profile.role


def get_or_create_bank_account(user):
    """Helper: get or auto-create bank account for a user."""
    account, created = BankAccount.objects.get_or_create(
        user=user,
        defaults={'account_number': BankAccount.generate_account_number()}
    )
    return account


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        ip_address = get_client_ip(request)
        
        # Check rate limiting
        is_limited, attempt_count = check_rate_limit(username, max_attempts=5, time_window_minutes=15)
        if is_limited:
            messages.error(request, "Terlalu banyak percobaan login gagal. Silakan coba lagi dalam 15 menit.")
            record_login_attempt(username, False, ip_address)
            log_audit(None, 'failed_login', request, f"Rate limit exceeded for {username}", status='failed')
            return redirect('login')
        
        # Try authentication
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            record_login_attempt(username, True, ip_address)
            log_audit(user, 'login', request, f"Successful login from {ip_address}")
            return redirect('dashboard')
        else:
            record_login_attempt(username, False, ip_address)
            log_audit(None, 'failed_login', request, f"Failed login attempt for {username}", status='failed')
            messages.error(request, "ID/Email atau Kata Sandi salah.")
    
    return render(request, 'login.html')


def register_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        username = request.POST.get('username')  # Nomor Rekening/ID
        email = request.POST.get('email')
        password = request.POST.get('password')

        if User.objects.filter(username=username).exists():
            messages.error(request, "ID sudah terdaftar.")
        else:
            user = User.objects.create_user(
                username=username, email=email,
                password=password, first_name=name
            )
            # Profile auto-created by signal with role='nasabah'
            # Also auto-create notification preference
            UserNotificationPreference.objects.create(user=user)
            KYCVerification.objects.create(user=user)
            user.save()
            
            log_audit(user, 'profile_update', request, "User registered")
            messages.success(request, "Akun berhasil dibuat. Silakan login.")
            return redirect('login')
    return render(request, 'register.html')


@login_required(login_url='login')
def dashboard_view(request):
    """Route user to their role-specific dashboard."""
    role = get_user_role(request.user)
    if role == 'admin':
        return redirect('dashboard_admin')
    elif role == 'teller':
        return redirect('dashboard_teller')
    elif role == 'cs':
        return redirect('dashboard_cs')
    else:
        return redirect('dashboard_nasabah')


@login_required(login_url='login')
def dashboard_admin_view(request):
    role = get_user_role(request.user)
    if role != 'admin':
        return redirect('dashboard')

    cs_wait = Queue.objects.filter(queue_type='CS', status='waiting').count()
    kasir_wait = Queue.objects.filter(queue_type='K', status='waiting').count()
    cs_done = Queue.objects.filter(queue_type='CS', status='done').count()
    kasir_done = Queue.objects.filter(queue_type='K', status='done').count()
    total_users = User.objects.count()
    total_tickets = SupportTicket.objects.count()

    context = {
        'role': role,
        'cs_wait': cs_wait,
        'kasir_wait': kasir_wait,
        'cs_done': cs_done,
        'kasir_done': kasir_done,
        'total_users': total_users,
        'total_tickets': total_tickets,
    }
    return render(request, 'dashboard_admin.html', context)


@login_required(login_url='login')
def dashboard_teller_view(request):
    role = get_user_role(request.user)
    if role != 'teller':
        return redirect('dashboard')
    return render(request, 'dashboard_teller.html', {'role': role})


@login_required(login_url='login')
def dashboard_cs_view(request):
    role = get_user_role(request.user)
    if role != 'cs':
        return redirect('dashboard')
    return render(request, 'dashboard_cs.html', {'role': role})


@login_required(login_url='login')
def dashboard_nasabah_view(request):
    role = get_user_role(request.user)
    if role != 'nasabah':
        return redirect('dashboard')

    account = get_or_create_bank_account(request.user)

    # 5 transaksi terbaru untuk dashboard
    recent_transactions = account.transactions.all()[:5]

    # Hitung total pemasukan & pengeluaran bulan ini
    from django.utils import timezone
    import calendar
    now = timezone.now()
    first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    monthly_in = sum(
        t.amount for t in account.transactions.filter(
            transaction_type__in=['credit', 'transfer_in'],
            created_at__gte=first_day
        )
    )
    monthly_out = sum(
        t.amount for t in account.transactions.filter(
            transaction_type__in=['debit', 'transfer_out'],
            created_at__gte=first_day
        )
    )

    context = {
        'role': role,
        'account': account,
        'recent_transactions': recent_transactions,
        'monthly_in': monthly_in,
        'monthly_out': monthly_out,
    }
    return render(request, 'dashboard_nasabah.html', context)


@login_required(login_url='login')
def mutasi_view(request):
    """Halaman mutasi rekening nasabah."""
    role = get_user_role(request.user)
    if role != 'nasabah':
        return redirect('dashboard')

    account = get_or_create_bank_account(request.user)
    transactions = account.transactions.all()

    # Filter by date
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    tx_type = request.GET.get('type', '')

    if start_date:
        transactions = transactions.filter(created_at__date__gte=start_date)
    if end_date:
        transactions = transactions.filter(created_at__date__lte=end_date)
    if tx_type:
        transactions = transactions.filter(transaction_type=tx_type)

    context = {
        'role': role,
        'account': account,
        'transactions': transactions,
        'start_date': start_date,
        'end_date': end_date,
        'tx_type': tx_type,
    }
    return render(request, 'mutasi.html', context)


@login_required(login_url='login')
def transfer_view(request):
    """Halaman transfer dana nasabah with OTP verification & recipient management."""
    role = get_user_role(request.user)
    if role != 'nasabah':
        return redirect('dashboard')

    account = get_or_create_bank_account(request.user)
    recipients = Recipient.objects.filter(user=request.user).order_by('-is_favorite')
    
    if request.method == 'POST':
        action = request.POST.get('action', 'transfer')
        
        if action == 'send_otp':
            # First step: validate transfer and send OTP
            dest_account_number = request.POST.get('dest_account', '').strip()
            amount_str = request.POST.get('amount', '0').replace('.', '').replace(',', '')
            description = request.POST.get('description', 'Transfer Dana').strip()
            
            # Validasi
            try:
                amount = Decimal(amount_str)
            except InvalidOperation:
                messages.error(request, "Jumlah transfer tidak valid.")
                return redirect('transfer')
            
            if amount <= 0:
                messages.error(request, "Jumlah transfer harus lebih dari 0.")
                return redirect('transfer')
            
            if dest_account_number == account.account_number:
                messages.error(request, "Tidak bisa transfer ke rekening sendiri.")
                return redirect('transfer')
            
            try:
                dest_account = BankAccount.objects.get(account_number=dest_account_number)
            except BankAccount.DoesNotExist:
                messages.error(request, f"Rekening tujuan {dest_account_number} tidak ditemukan.")
                return redirect('transfer')
            
            # Calculate fee
            fee_model = TransactionFee.objects.filter(
                transaction_type='transfer_internal',
                is_active=True
            ).first()
            fee = Decimal(0)
            if fee_model:
                fee = fee_model.calculate_fee(amount)
            
            total_amount = amount + (fee or Decimal(0))
            
            if account.balance < total_amount:
                messages.error(request, f"Saldo tidak mencukupi. Dibutuhkan Rp {total_amount:,.0f} (termasuk biaya Rp {fee:,.0f}).")
                return redirect('transfer')
            
            # Check fraud
            is_fraud, alerts = check_fraud(request.user, 'transfer_out', amount)
            if is_fraud:
                messages.warning(request, "Aktivitas Anda terdeteksi mencurigakan. Verifikasi tambahan diperlukan.")
            
            # Send OTP
            send_otp(request.user, 'transfer')
            request.session['transfer_data'] = {
                'dest_account_number': dest_account_number,
                'dest_account_name': dest_account.user.first_name,
                'amount': str(amount),
                'fee': str(fee),
                'total': str(total_amount),
                'description': description
            }
            
            log_audit(request.user, 'transfer', request, f"Transfer initiation: {amount} to {dest_account_number}")
            messages.info(request, f"Kode OTP telah dikirim ke email Anda. Jumlah: Rp {amount:,.0f} + biaya Rp {fee:,.0f}")
            return redirect('transfer_verify')
        
        elif action == 'add_recipient':
            # Add new recipient
            recipient_account = request.POST.get('recipient_account', '').strip()
            recipient_name = request.POST.get('recipient_name', '').strip()
            
            try:
                dest_account = BankAccount.objects.get(account_number=recipient_account)
                Recipient.objects.get_or_create(
                    user=request.user,
                    account_number=recipient_account,
                    defaults={
                        'recipient_name': recipient_name or dest_account.user.first_name,
                        'bank_name': 'Bank Indonesia'
                    }
                )
                messages.success(request, "Penerima berhasil ditambahkan!")
                log_audit(request.user, 'recipient_add', request, f"Added recipient: {recipient_name}")
            except BankAccount.DoesNotExist:
                messages.error(request, "Rekening tidak ditemukan.")
    
    context = {
        'role': role,
        'account': account,
        'recipients': recipients,
    }
    return render(request, 'transfer.html', context)


@login_required(login_url='login')
def transfer_verify(request):
    """Verify transfer dengan OTP."""
    role = get_user_role(request.user)
    if role != 'nasabah':
        return redirect('dashboard')
    
    transfer_data = request.session.get('transfer_data')
    if not transfer_data:
        messages.error(request, "Data transfer tidak ditemukan.")
        return redirect('transfer')
    
    if request.method == 'POST':
        otp_code = request.POST.get('otp_code', '').strip()
        
        is_valid, msg = verify_otp(request.user, otp_code, 'transfer')
        if not is_valid:
            messages.error(request, msg)
            return redirect('transfer_verify')
        
        # Process the transfer
        account = get_or_create_bank_account(request.user)
        dest_account_number = transfer_data['dest_account_number']
        amount = Decimal(transfer_data['amount'])
        fee = Decimal(transfer_data['fee'])
        description = transfer_data['description']
        
        try:
            dest_account = BankAccount.objects.get(account_number=dest_account_number)
        except BankAccount.DoesNotExist:
            messages.error(request, "Rekening tujuan tidak ditemukan.")
            return redirect('transfer')
        
        # Update balances
        account.balance -= (amount + fee)
        account.save()
        
        dest_account.balance += amount
        dest_account.save()
        
        # Create transactions
        Transaction.objects.create(
            account=account,
            transaction_type='transfer_out',
            amount=amount + fee,
            description=description or f"Transfer ke {dest_account_number}",
            related_account=dest_account_number,
            balance_after=account.balance,
        )
        Transaction.objects.create(
            account=dest_account,
            transaction_type='transfer_in',
            amount=amount,
            description=f"Transfer dari {account.account_number}",
            related_account=account.account_number,
            balance_after=dest_account.balance,
        )
        
        # Create notifications
        create_notification(
            request.user,
            "Transfer Berhasil",
            f"Transfer Rp {amount:,.0f} ke {transfer_data['dest_account_name']} berhasil!",
            'transfer'
        )
        create_notification(
            dest_account.user,
            "Transfer Masuk",
            f"Anda menerima transfer Rp {amount:,.0f} dari {account.user.first_name}",
            'transfer'
        )
        
        # Send emails
        send_email_notification(
            request.user,
            "Konfirmasi Transfer",
            f"Transfer Rp {amount:,.0f} ke {transfer_data['dest_account_name']} ({dest_account_number}) berhasil diproses."
        )
        
        log_audit(request.user, 'transfer', request, f"Transfer completed: {amount} to {dest_account_number}")
        
        # Clear session data
        del request.session['transfer_data']
        
        messages.success(request, f"Transfer Rp {amount:,.0f} ke {transfer_data['dest_account_name']} berhasil!")
        return redirect('transfer')
    
    context = {
        'role': role,
        'transfer_data': transfer_data,
    }
    return render(request, 'transfer_verify.html', context)


@login_required(login_url='login')
def tiket_view(request):
    """Halaman pusat bantuan / tiket nasabah."""
    role = get_user_role(request.user)
    if role != 'nasabah':
        return redirect('dashboard')

    if request.method == 'POST':
        category = request.POST.get('category')
        detail = request.POST.get('detail')
        SupportTicket.objects.create(
            user=request.user,
            name=request.user.first_name or request.user.username,
            category=category,
            detail=detail,
            status='open'
        )
        messages.success(request, "Tiket bantuan Anda berhasil dikirim. Tim CS akan segera menghubungi Anda.")
        return redirect('tiket')

    # Ambil tiket milik user ini
    user_tickets = SupportTicket.objects.filter(user=request.user)
    category_choices = SupportTicket.CATEGORY_CHOICES

    context = {
        'role': role,
        'user_tickets': user_tickets,
        'category_choices': category_choices,
    }
    return render(request, 'tiket.html', context)


def api_dashboard_data(request):
    q_type_filter = request.GET.get('type', None)  # 'CS', 'K', or None for all

    cs_wait = Queue.objects.filter(queue_type='CS', status='waiting').count()
    kasir_wait = Queue.objects.filter(queue_type='K', status='waiting').count()

    current_cs = Queue.objects.filter(queue_type='CS', status='calling').first()
    current_kasir = Queue.objects.filter(queue_type='K', status='calling').first()

    # Build recent queues (filter by type if specified)
    recent_qs_query = Queue.objects.filter(status='done').order_by('-updated_at')
    if q_type_filter:
        recent_qs_query = recent_qs_query.filter(queue_type=q_type_filter)
    recent_qs = recent_qs_query[:5]

    recent_queues = []
    for q in recent_qs:
        recent_queues.append({
            'num': f"{q.queue_type}-{q.number}",
            'type': 'Kasir' if q.queue_type == 'K' else 'CS',
            'time': q.updated_at.strftime('%H:%M')
        })

    return JsonResponse({
        'cs_wait': cs_wait,
        'kasir_wait': kasir_wait,
        'current_cs': f"CS-{current_cs.number}" if current_cs else "-",
        'current_cs_loket': f"Loket {current_cs.counter}" if current_cs and current_cs.counter else "-",
        'current_kasir': f"K-{current_kasir.number}" if current_kasir else "-",
        'current_kasir_loket': f"Loket {current_kasir.counter}" if current_kasir and current_kasir.counter else "-",
        'recent_queues': recent_queues
    })


def api_take_queue(request):
    """Nasabah takes a queue number."""
    if request.method == 'POST':
        data = json.loads(request.body)
        q_type = data.get('type')
        if q_type in ['CS', 'K']:
            last_q = Queue.objects.filter(queue_type=q_type).order_by('-id').first()
            if last_q:
                try:
                    next_num = str(int(last_q.number) + 1).zfill(3)
                except:
                    next_num = "001"
            else:
                next_num = "001"
            Queue.objects.create(queue_type=q_type, number=next_num, status='waiting')
            return JsonResponse({'status': 'ok', 'number': f"{q_type}-{next_num}"})
    return JsonResponse({'status': 'error'})


def api_call_queue(request):
    """Teller/CS calls the next queue."""
    if request.method == 'POST':
        data = json.loads(request.body)
        q_type = data.get('type')
        loket = data.get('loket', 1)

        # Verify role permission
        if request.user.is_authenticated:
            role = get_user_role(request.user)
            if role == 'teller' and q_type != 'K':
                return JsonResponse({'status': 'error', 'msg': 'Teller hanya dapat memanggil antrean Kasir.'})
            if role == 'cs' and q_type != 'CS':
                return JsonResponse({'status': 'error', 'msg': 'CS hanya dapat memanggil antrean Customer Service.'})

        # Mark current calling queue as done
        current_calling = Queue.objects.filter(queue_type=q_type, status='calling')
        for q in current_calling:
            q.status = 'done'
            q.save()

        # Call next waiting queue
        next_q = Queue.objects.filter(queue_type=q_type, status='waiting').order_by('id').first()
        if next_q:
            next_q.status = 'calling'
            next_q.counter = int(loket)
            next_q.save()
            return JsonResponse({'status': 'ok', 'called': f"{q_type}-{next_q.number}"})
        return JsonResponse({'status': 'empty'})
    return JsonResponse({'status': 'error'})


@login_required(login_url='login')
def support_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        category = request.POST.get('category')
        detail = request.POST.get('detail')
        SupportTicket.objects.create(name=name, category=category, detail=detail)
        messages.success(request, "Pesan Anda berhasil dikirim.")
        return redirect('support')
    return render(request, 'support.html', {'role': get_user_role(request.user)})


def logout_view(request):
    if request.user.is_authenticated:
        log_audit(request.user, 'logout', request, "User logged out")
    logout(request)
    return redirect('login')


# ==================== NEW FEATURES ====================

@login_required(login_url='login')
def kyc_profile_view(request):
    """Complete KYC profile and identity verification."""
    role = get_user_role(request.user)
    if role != 'nasabah':
        return redirect('dashboard')
    
    kyc, created = KYCVerification.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        kyc.full_name = request.POST.get('full_name', kyc.full_name)
        kyc.date_of_birth = request.POST.get('date_of_birth', kyc.date_of_birth)
        kyc.address = request.POST.get('address', kyc.address)
        kyc.city = request.POST.get('city', kyc.city)
        kyc.province = request.POST.get('province', kyc.province)
        kyc.postal_code = request.POST.get('postal_code', kyc.postal_code)
        kyc.document_type = request.POST.get('document_type', kyc.document_type)
        kyc.document_number = request.POST.get('document_number', kyc.document_number)
        
        # In production, handle file uploads for document_image_url and selfie_image_url
        kyc.status = 'under_review'
        kyc.save()
        
        log_audit(request.user, 'kyc_submit', request, "KYC profile submitted for verification")
        create_notification(request.user, "KYC Submitted", "Profil KYC Anda telah diterima dan sedang dalam proses verifikasi.", 'system')
        messages.success(request, "Profil KYC Anda berhasil dikirim untuk verifikasi. Kami akan segera memproses.")
        return redirect('dashboard_nasabah')
    
    context = {
        'role': role,
        'kyc': kyc,
        'document_types': KYCVerification.DOCUMENT_TYPES,
    }
    return render(request, 'kyc_profile.html', context)


@login_required(login_url='login')
def recipients_view(request):
    """Manage saved recipients/payees."""
    role = get_user_role(request.user)
    if role != 'nasabah':
        return redirect('dashboard')
    
    recipients = Recipient.objects.filter(user=request.user).order_by('-is_favorite', '-created_at')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            account_number = request.POST.get('account_number', '').strip()
            recipient_name = request.POST.get('recipient_name', '').strip()
            
            try:
                BankAccount.objects.get(account_number=account_number)
                recipient, created = Recipient.objects.get_or_create(
                    user=request.user,
                    account_number=account_number,
                    defaults={
                        'recipient_name': recipient_name,
                        'bank_name': 'Bank Indonesia'
                    }
                )
                if created:
                    messages.success(request, "Penerima berhasil ditambahkan!")
                    log_audit(request.user, 'recipient_add', request, f"Added recipient: {recipient_name}")
                else:
                    messages.info(request, "Penerima sudah ada di daftar Anda.")
            except BankAccount.DoesNotExist:
                messages.error(request, "Rekening tidak ditemukan.")
        
        elif action == 'delete':
            recipient_id = request.POST.get('recipient_id')
            try:
                recipient = Recipient.objects.get(id=recipient_id, user=request.user)
                recipient.delete()
                messages.success(request, "Penerima berhasil dihapus.")
            except Recipient.DoesNotExist:
                messages.error(request, "Penerima tidak ditemukan.")
        
        elif action == 'favorite':
            recipient_id = request.POST.get('recipient_id')
            try:
                recipient = Recipient.objects.get(id=recipient_id, user=request.user)
                recipient.is_favorite = not recipient.is_favorite
                recipient.save()
                messages.success(request, "Status favorit berhasil diupdate.")
            except Recipient.DoesNotExist:
                messages.error(request, "Penerima tidak ditemukan.")
        
        return redirect('recipients')
    
    context = {
        'role': role,
        'recipients': recipients,
    }
    return render(request, 'recipients.html', context)


@login_required(login_url='login')
def scheduled_transfer_view(request):
    """Manage scheduled/recurring transfers."""
    role = get_user_role(request.user)
    if role != 'nasabah':
        return redirect('dashboard')
    
    account = get_or_create_bank_account(request.user)
    scheduled_txs = ScheduledTransaction.objects.filter(account=account)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create':
            recipient_account = request.POST.get('recipient_account', '').strip()
            recipient_name = request.POST.get('recipient_name', '').strip()
            amount_str = request.POST.get('amount', '0').replace('.', '').replace(',', '')
            frequency = request.POST.get('frequency', 'monthly')
            start_date = request.POST.get('start_date')
            description = request.POST.get('description', '')
            
            try:
                amount = Decimal(amount_str)
                BankAccount.objects.get(account_number=recipient_account)
                
                from datetime import datetime
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                
                ScheduledTransaction.objects.create(
                    account=account,
                    recipient_account=recipient_account,
                    recipient_name=recipient_name,
                    amount=amount,
                    frequency=frequency,
                    start_date=start_dt.date(),
                    next_execution=timezone.now(),
                    description=description
                )
                
                messages.success(request, "Transfer terjadwal berhasil dibuat!")
                log_audit(request.user, 'scheduled_tx', request, f"Created scheduled transfer to {recipient_name}")
            except Exception as e:
                messages.error(request, f"Gagal membuat transfer terjadwal: {str(e)}")
        
        elif action == 'pause':
            scheduled_id = request.POST.get('scheduled_id')
            try:
                scheduled = ScheduledTransaction.objects.get(id=scheduled_id, account=account)
                scheduled.status = 'paused'
                scheduled.save()
                messages.success(request, "Transfer terjadwal dijeda.")
            except ScheduledTransaction.DoesNotExist:
                messages.error(request, "Transfer tidak ditemukan.")
        
        elif action == 'resume':
            scheduled_id = request.POST.get('scheduled_id')
            try:
                scheduled = ScheduledTransaction.objects.get(id=scheduled_id, account=account)
                scheduled.status = 'active'
                scheduled.save()
                messages.success(request, "Transfer terjadwal dilanjutkan.")
            except ScheduledTransaction.DoesNotExist:
                messages.error(request, "Transfer tidak ditemukan.")
        
        elif action == 'cancel':
            scheduled_id = request.POST.get('scheduled_id')
            try:
                scheduled = ScheduledTransaction.objects.get(id=scheduled_id, account=account)
                scheduled.status = 'cancelled'
                scheduled.save()
                messages.success(request, "Transfer terjadwal dibatalkan.")
            except ScheduledTransaction.DoesNotExist:
                messages.error(request, "Transfer tidak ditemukan.")
        
        return redirect('scheduled_transfer')
    
    context = {
        'role': role,
        'account': account,
        'scheduled_txs': scheduled_txs,
        'frequencies': ScheduledTransaction.FREQUENCY_CHOICES,
    }
    return render(request, 'scheduled_transfer.html', context)


@login_required(login_url='login')
def statement_export_view(request):
    """Export account statement in various formats."""
    role = get_user_role(request.user)
    if role != 'nasabah':
        return redirect('dashboard')
    
    account = get_or_create_bank_account(request.user)
    
    if request.method == 'POST':
        export_format = request.POST.get('format', 'pdf')
        start_date = request.POST.get('start_date', '')
        end_date = request.POST.get('end_date', '')
        
        transactions = account.transactions.all()
        
        if start_date:
            transactions = transactions.filter(created_at__date__gte=start_date)
        if end_date:
            transactions = transactions.filter(created_at__date__lte=end_date)
        
        if export_format == 'csv':
            csv_content = export_transactions_csv(transactions)
            response = HttpResponse(csv_content, content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="statement_{account.account_number}.csv"'
            return response
        
        elif export_format == 'pdf':
            pdf_content = export_transactions_pdf(transactions, request.user)
            response = HttpResponse(pdf_content, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="statement_{account.account_number}.pdf"'
            return response
    
    context = {
        'role': role,
        'account': account,
        'formats': [('csv', 'CSV'), ('pdf', 'PDF')],
    }
    return render(request, 'statement_export.html', context)


@login_required(login_url='login')
def notification_preference_view(request):
    """Manage notification preferences."""
    role = get_user_role(request.user)
    
    prefs, created = UserNotificationPreference.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        prefs.email_on_transfer = request.POST.get('email_on_transfer') == 'on'
        prefs.email_on_login = request.POST.get('email_on_login') == 'on'
        prefs.email_on_kyc = request.POST.get('email_on_kyc') == 'on'
        prefs.email_daily_summary = request.POST.get('email_daily_summary') == 'on'
        prefs.sms_on_large_transfer = request.POST.get('sms_on_large_transfer') == 'on'
        prefs.push_notifications = request.POST.get('push_notifications') == 'on'
        
        try:
            sms_threshold = Decimal(request.POST.get('sms_threshold', prefs.sms_threshold))
            prefs.sms_threshold = sms_threshold
        except:
            pass
        
        prefs.save()
        messages.success(request, "Preferensi notifikasi berhasil diupdate.")
        return redirect('dashboard_nasabah')
    
    context = {
        'role': role,
        'prefs': prefs,
    }
    return render(request, 'notification_preference.html', context)


@login_required(login_url='login')
def fraud_alerts_view(request):
    """View fraud alerts."""
    role = get_user_role(request.user)
    if role != 'nasabah':
        return redirect('dashboard')
    
    alerts = FraudAlert.objects.filter(user=request.user).order_by('-created_at')
    
    if request.method == 'POST':
        alert_id = request.POST.get('alert_id')
        action = request.POST.get('action')
        
        try:
            alert = FraudAlert.objects.get(id=alert_id, user=request.user)
            
            if action == 'confirm_safe':
                alert.is_resolved = True
                alert.action_taken = 'User confirmed account is safe'
                alert.save()
                messages.success(request, "Terima kasih. Kami akan memantau akun Anda lebih ketat.")
            
            elif action == 'confirm_fraud':
                alert.is_resolved = True
                alert.action_taken = 'User reported account compromised'
                alert.save()
                messages.warning(request, "Hubungi customer service kami segera untuk keamanan akun Anda.")
        
        except FraudAlert.DoesNotExist:
            messages.error(request, "Alert tidak ditemukan.")
        
        return redirect('fraud_alerts')
    
    context = {
        'role': role,
        'alerts': alerts,
    }
    return render(request, 'fraud_alerts.html', context)


@login_required(login_url='login')
def audit_log_view(request):
    """View audit logs of user activities."""
    role = get_user_role(request.user)
    if role != 'nasabah':
        return redirect('dashboard')
    
    logs = AuditLog.objects.filter(user=request.user).order_by('-created_at')[:100]
    
    context = {
        'role': role,
        'logs': logs,
    }
    return render(request, 'audit_log.html', context)


@login_required(login_url='login')
def admin_analytics_view(request):
    """Admin analytics and reporting dashboard."""
    role = get_user_role(request.user)
    if role != 'admin':
        return redirect('dashboard')
    
    # Calculate statistics
    total_users = User.objects.count()
    total_accounts = BankAccount.objects.count()
    total_balance = BankAccount.objects.aggregate(Sum('balance'))['balance__sum'] or Decimal(0)
    
    # Transaction stats
    total_transactions = Transaction.objects.count()
    today_transactions = Transaction.objects.filter(created_at__date=timezone.now().date()).count()
    
    # Calculate total transaction volume
    total_volume = Transaction.objects.aggregate(Sum('amount'))['amount__sum'] or Decimal(0)
    
    # Recent transactions
    recent_transactions = Transaction.objects.order_by('-created_at')[:10]
    
    # KYC stats
    kyc_pending = KYCVerification.objects.filter(status='pending').count()
    kyc_approved = KYCVerification.objects.filter(status='approved').count()
    
    # Fraud alerts
    active_fraud_alerts = FraudAlert.objects.filter(is_resolved=False).count()
    
    # Support tickets
    open_tickets = SupportTicket.objects.filter(status='open').count()
    
    context = {
        'role': role,
        'total_users': total_users,
        'total_accounts': total_accounts,
        'total_balance': total_balance,
        'total_transactions': total_transactions,
        'today_transactions': today_transactions,
        'total_volume': total_volume,
        'recent_transactions': recent_transactions,
        'kyc_pending': kyc_pending,
        'kyc_approved': kyc_approved,
        'active_fraud_alerts': active_fraud_alerts,
        'open_tickets': open_tickets,
    }
    return render(request, 'admin_analytics.html', context)


@login_required(login_url='login')
def admin_kyc_review_view(request):
    """Admin review KYC submissions."""
    role = get_user_role(request.user)
    if role != 'admin':
        return redirect('dashboard')
    
    kyc_submissions = KYCVerification.objects.filter(status__in=['pending', 'under_review']).order_by('created_at')
    
    if request.method == 'POST':
        kyc_id = request.POST.get('kyc_id')
        action = request.POST.get('action')
        rejection_reason = request.POST.get('rejection_reason', '')
        
        try:
            kyc = KYCVerification.objects.get(id=kyc_id)
            
            if action == 'approve':
                kyc.status = 'approved'
                kyc.verified_at = timezone.now()
                kyc.save()
                create_notification(kyc.user, "KYC Approved", "Profil KYC Anda telah disetujui!", 'system')
                send_email_notification(kyc.user, "KYC Approved", "Selamat, profil KYC Anda telah diverifikasi dan disetujui.")
                messages.success(request, "KYC approved.")
                log_audit(request.user, 'kyc_submit', request, f"Approved KYC for {kyc.user.username}")
            
            elif action == 'reject':
                kyc.status = 'rejected'
                kyc.rejection_reason = rejection_reason
                kyc.save()
                create_notification(kyc.user, "KYC Rejected", f"Profil KYC Anda ditolak: {rejection_reason}", 'system')
                messages.success(request, "KYC rejected.")
                log_audit(request.user, 'kyc_submit', request, f"Rejected KYC for {kyc.user.username}")
        
        except KYCVerification.DoesNotExist:
            messages.error(request, "KYC tidak ditemukan.")
        
        return redirect('admin_kyc_review')
    
    context = {
        'role': role,
        'kyc_submissions': kyc_submissions,
    }
    return render(request, 'admin_kyc_review.html', context)


@login_required(login_url='login')
def admin_fraud_management_view(request):
    """Admin manage fraud alerts."""
    role = get_user_role(request.user)
    if role != 'admin':
        return redirect('dashboard')
    
    alerts = FraudAlert.objects.all().order_by('-created_at')
    unresolved_alerts = alerts.filter(is_resolved=False)
    
    if request.method == 'POST':
        alert_id = request.POST.get('alert_id')
        action = request.POST.get('action')
        action_taken = request.POST.get('action_taken', '')
        
        try:
            alert = FraudAlert.objects.get(id=alert_id)
            
            if action == 'mark_resolved':
                alert.is_resolved = True
                alert.action_taken = action_taken
                alert.save()
                messages.success(request, "Alert ditandai sebagai resolved.")
                log_audit(request.user, 'system', request, f"Resolved fraud alert for {alert.user.username}")
            
            elif action == 'lock_account':
                alert.user.profile.account_locked = True
                alert.user.profile.save()
                alert.is_resolved = True
                alert.action_taken = 'Account locked'
                alert.save()
                create_notification(alert.user, "Account Locked", "Akun Anda telah dikunci untuk keamanan. Hubungi customer service.", 'system')
                messages.success(request, "Account locked.")
        
        except FraudAlert.DoesNotExist:
            messages.error(request, "Alert tidak ditemukan.")
        
        return redirect('admin_fraud_management')
    
    context = {
        'role': role,
        'alerts': alerts,
        'unresolved_count': unresolved_alerts.count(),
    }
    return render(request, 'admin_fraud_management.html', context)
