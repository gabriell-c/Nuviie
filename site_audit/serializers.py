from rest_framework import serializers
from .models import SiteAuditReport


class SiteAuditReportSerializer(serializers.ModelSerializer):
    lead_name = serializers.CharField(source='lead.name', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = SiteAuditReport
        fields = [
            'id', 'url', 'status', 'status_display', 'lead', 'lead_name',
            'scores', 'core_web_vitals', 'recommendations', 'summary',
            'error_message', 'created_at', 'completed_at',
        ]
        read_only_fields = [
            'id', 'status', 'scores', 'core_web_vitals', 'recommendations',
            'summary', 'error_message', 'created_at', 'completed_at',
        ]


class SiteAuditCreateSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=500)
    lead_id = serializers.IntegerField(required=False, allow_null=True)
