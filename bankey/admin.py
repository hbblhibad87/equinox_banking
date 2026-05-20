from django.contrib import admin
from .models import UserProfile, Queue, SupportTicket, BankAccount, Transaction


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
    list_display = ('name', 'category', 'status', 'created_at')
    list_filter = ('category', 'status')
    search_fields = ('name', 'detail')


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('account_number', 'user', 'balance', 'created_at')
    search_fields = ('account_number', 'user__username', 'user__first_name')
    readonly_fields = ('account_number', 'created_at')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('account', 'transaction_type', 'amount', 'balance_after', 'created_at')
    list_filter = ('transaction_type',)
    search_fields = ('account__account_number', 'description')
    readonly_fields = ('created_at',)
