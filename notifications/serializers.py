from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    lead_name = serializers.CharField(source='lead.name', read_only=True, allow_null=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'message', 'level', 'lead', 'lead_name',
            'trigger_date', 'read_at', 'created_at',
        ]
