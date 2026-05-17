from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from .models import Queue, SupportTicket, UserProfile
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


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
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
            user.save()
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
    return render(request, 'dashboard_nasabah.html', {'role': role})


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
    logout(request)
    return redirect('login')
