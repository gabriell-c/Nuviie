from rest_framework import serializers

from .models import WhatsAppInstance, WhatsAppMessage


class WhatsAppInstanceSerializer(serializers.ModelSerializer):
    is_connected = serializers.BooleanField(read_only=True)

    class Meta:
        model = WhatsAppInstance
        fields = [
            'id', 'name', 'instance_name', 'phone_number',
            'status', 'is_connected', 'is_default', 'is_active',
            'ai_autoreply_enabled', 'ai_mode',
            'last_connected_at', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'status', 'is_connected', 'last_connected_at', 'created_at', 'updated_at',
        ]


class WhatsAppMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhatsAppMessage
        fields = [
            'id', 'instance', 'lead', 'direction', 'phone', 'contact_name',
            'message_type', 'text', 'media_url', 'status', 'evolution_id',
            'error', 'timestamp', 'created_at',
        ]
        read_only_fields = fields
