from django.db import models

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
