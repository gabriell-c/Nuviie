from django.contrib import admin

from .models import WhatsAppInstance, WhatsAppMessage


@admin.register(WhatsAppInstance)
class WhatsAppInstanceAdmin(admin.ModelAdmin):
    list_display = ('name', 'instance_name', 'phone_number', 'status', 'is_default', 'is_active', 'user')
    list_filter = ('status', 'is_default', 'is_active')
    search_fields = ('name', 'instance_name', 'phone_number')
    readonly_fields = ('last_qr_base64', 'last_connected_at', 'created_at', 'updated_at')


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'direction', 'phone', 'contact_name', 'message_type', 'status', 'lead')
    list_filter = ('direction', 'status', 'message_type')
    search_fields = ('phone', 'contact_name', 'text', 'evolution_id')
    readonly_fields = ('raw', 'created_at')
    raw_id_fields = ('lead', 'instance', 'user')
