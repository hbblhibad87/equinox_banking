import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
django.setup()

from django.contrib.auth.models import User
from bankey.models import UserProfile

# ============================================
# Demo Accounts for Equinox Banking
# ============================================

DEMO_USERS = [
    {
        'username': 'admin',
        'email': 'admin@equinoxbanking.com',
        'password': 'admin123',
        'first_name': 'Admin',
        'is_superuser': True,
        'is_staff': True,
        'role': 'admin',
    },
    {
        'username': 'teller01',
        'email': 'teller@equinoxbanking.com',
        'password': 'teller123',
        'first_name': 'Budi Santoso',
        'is_superuser': False,
        'is_staff': False,
        'role': 'teller',
    },
    {
        'username': 'cs01',
        'email': 'cs@equinoxbanking.com',
        'password': 'cs123',
        'first_name': 'Sari Dewi',
        'is_superuser': False,
        'is_staff': False,
        'role': 'cs',
    },
    {
        'username': 'nasabah01',
        'email': 'nasabah@equinoxbanking.com',
        'password': 'nasabah123',
        'first_name': 'Andi Pratama',
        'is_superuser': False,
        'is_staff': False,
        'role': 'nasabah',
    },
]

print("=" * 50)
print("  Equinox Banking — Demo Account Setup")
print("=" * 50)

for data in DEMO_USERS:
    user, created = User.objects.get_or_create(
        username=data['username'],
        defaults={
            'email': data['email'],
            'first_name': data['first_name'],
            'is_superuser': data['is_superuser'],
            'is_staff': data['is_staff'],
        }
    )
    if created:
        user.set_password(data['password'])
        user.save()

    # Create or update profile
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.role = data['role']
    profile.save()

    status = "CREATED" if created else "EXISTS"
    print(f"  [{status}] {data['role'].upper():8s} | {data['username']:12s} | {data['email']}")

print()
print("  Demo Credentials:")
print("  -" * 25)
print("  Admin    : admin    / admin123")
print("  Teller   : teller01 / teller123")
print("  CS       : cs01     / cs123")
print("  Nasabah  : nasabah01/ nasabah123")
print("=" * 50)
