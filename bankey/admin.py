from django.contrib import admin
from .models import UserProfile, Queue, SupportTicket


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__email')


@admin.register(Queue)
class QueueAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'queue_type', 'status', 'counter', 'created_at')
    list_filter = ('queue_type', 'status')
    search_fields = ('number',)


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'created_at')
    list_filter = ('category',)
    search_fields = ('name', 'detail')
