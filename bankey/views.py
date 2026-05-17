from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.contrib import messages
from .models import Queue, SupportTicket

def login_view(request):
    if request.method == 'POST':
        # Simple implementation for demo purposes
        # Assuming email/ID field is mapped to username
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
        username = request.POST.get('username') # using as Nomor Rekening/ID
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, "ID sudah terdaftar.")
        else:
            user = User.objects.create_user(username=username, email=email, password=password, first_name=name)
            user.save()
            messages.success(request, "Akun berhasil dibuat. Silakan login.")
            return redirect('login')
    return render(request, 'register.html')

def dashboard_view(request):
    return render(request, 'dashboard.html')

from django.http import JsonResponse
import json

def api_dashboard_data(request):
    # Hitung jumlah antrean
    cs_wait = Queue.objects.filter(queue_type='CS', status='waiting').count()
    kasir_wait = Queue.objects.filter(queue_type='K', status='waiting').count()
    
    # Ambil yang sedang dipanggil
    current_cs = Queue.objects.filter(queue_type='CS', status='calling').first()
    current_kasir = Queue.objects.filter(queue_type='K', status='calling').first()
    
    # Ambil 5 antrean terakhir yang selesai
    recent_qs = Queue.objects.filter(status='done').order_by('-updated_at')[:5]
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
            return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'})

def api_call_queue(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        q_type = data.get('type')
        loket = data.get('loket', 1)
        
        # Selesaikan antrean yang sedang dipanggil sekarang
        current_calling = Queue.objects.filter(queue_type=q_type, status='calling')
        for q in current_calling:
            q.status = 'done'
            q.save()
            
        # Panggil antrean berikutnya
        next_q = Queue.objects.filter(queue_type=q_type, status='waiting').order_by('id').first()
        if next_q:
            next_q.status = 'calling'
            next_q.counter = int(loket)
            next_q.save()
            return JsonResponse({'status': 'ok', 'called': f"{q_type}-{next_q.number}"})
        return JsonResponse({'status': 'empty'})
    return JsonResponse({'status': 'error'})

def support_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        category = request.POST.get('category')
        detail = request.POST.get('detail')
        SupportTicket.objects.create(name=name, category=category, detail=detail)
        messages.success(request, "Pesan Anda berhasil dikirim.")
        return redirect('support')
    return render(request, 'support.html')

def logout_view(request):
    logout(request)
    return redirect('login')
