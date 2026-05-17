from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('teller', 'Teller (Kasir)'),
        ('cs', 'Customer Service'),
        ('nasabah', 'Nasabah'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='nasabah')

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Auto-create UserProfile when a new User is created."""
    if created:
        role = 'admin' if instance.is_superuser else 'nasabah'
        UserProfile.objects.get_or_create(user=instance, defaults={'role': role})


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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.queue_type}-{self.number}"


class SupportTicket(models.Model):
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50)
    detail = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.category}"
