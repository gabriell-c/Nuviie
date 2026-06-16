from rest_framework import serializers
from .models import Lead, LeadNote
from .website_utils import detect_website_type

class LeadNoteSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    action_type_display = serializers.CharField(source='get_action_type_display', read_only=True)
    created_at_formatted = serializers.SerializerMethodField()

    class Meta:
        model = LeadNote
        fields = ['id', 'user_name', 'note', 'action_type', 'action_type_display', 'created_at', 'created_at_formatted']
        read_only_fields = ['id', 'created_at']

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def get_created_at_formatted(self, obj):
        return obj.created_at.strftime('%d/%m/%Y %H:%M')


class LeadSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    website_detected_type_display = serializers.CharField(
        source='get_website_detected_type_display', read_only=True
    )
    whatsapp_link = serializers.SerializerMethodField()
    maps_link = serializers.SerializerMethodField()
    instagram_link = serializers.SerializerMethodField()
    profile_picture_display_url = serializers.SerializerMethodField()
    notes = LeadNoteSerializer(many=True, read_only=True)
    deadline_urgency = serializers.SerializerMethodField()
    days_until_deadline = serializers.SerializerMethodField()
    contract_summary = serializers.SerializerMethodField()
    site_audit_summary = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = [
            'id', 'name', 'category', 'city', 'phone_number', 'normalized_phone',
            'website', 'website_detected_type', 'website_detected_type_display',
            'instagram', 'instagram_link', 'facebook', 'youtube', 'twitter', 'linkedin',
            'bio', 'address', 'rating', 'review_count',
            'recent_reviews', 'business_hours',
            'maps_url', 'maps_share_url', 'maps_link',
            'preview_site_url', 'final_site_url',
            'contract', 'project_deadline', 'contract_value',
            'deadline_urgency', 'days_until_deadline', 'contract_summary',
            'site_audit_summary',
            'source', 'source_display', 'status', 'status_display',
            'quality_score', 'score_breakdown', 'is_verified', 'whatsapp_link',
            'price_range', 'plus_code', 'amenities', 'total_photos',
            'profile_picture_url', 'profile_picture_display_url',
            'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'normalized_phone', 'quality_score', 'score_breakdown',
            'created_at', 'updated_at'
        ]

    def get_whatsapp_link(self, obj):
        return obj.get_whatsapp_link()

    def get_maps_link(self, obj):
        return obj.get_maps_link()

    def get_instagram_link(self, obj):
        if obj.instagram:
            handle = str(obj.instagram).strip().lstrip('@')
            if handle:
                return f'https://www.instagram.com/{handle}/'
        if obj.source == 'instagram' and obj.maps_url and 'instagram.com' in (obj.maps_url or ''):
            return obj.maps_url
        if isinstance(obj.amenities, dict) and obj.amenities.get('instagram_url'):
            return obj.amenities['instagram_url']
        return None

    def get_profile_picture_display_url(self, obj):
        from .profile_picture_utils import get_profile_picture_display_url
        request = self.context.get('request')
        return get_profile_picture_display_url(obj, request)

    def get_deadline_urgency(self, obj):
        return obj.deadline_urgency()

    def get_days_until_deadline(self, obj):
        return obj.days_until_deadline()

    def get_contract_summary(self, obj):
        if not obj.contract_id:
            return None
        c = obj.contract
        return {
            'id': c.id,
            'client_name': c.client_name or c.name,
            'payment_mode': (c.payment_plan or {}).get('mode'),
            'download_path': f'/contracts/history/{c.id}/download/',
        }

    def get_site_audit_summary(self, obj):
        try:
            from site_audit.lead_integration import build_site_audit_summary
            return build_site_audit_summary(obj)
        except Exception:
            return None

    def _normalize_phone(self, phone):
        import re
        cleaned = "".join(c for c in str(phone) if c.isdigit())
        if cleaned:
            if len(cleaned) <= 11 and not cleaned.startswith('55'):
                cleaned = "55" + cleaned
            return cleaned
        return None

    def _apply_website_type(self, validated_data):
        website = validated_data.get('website')
        if website and 'website_detected_type' not in validated_data:
            validated_data['website_detected_type'] = detect_website_type(website)

    def create(self, validated_data):
        phone = validated_data.get('phone_number')
        if phone:
            validated_data['normalized_phone'] = self._normalize_phone(phone)
        self._apply_website_type(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        phone = validated_data.get('phone_number', instance.phone_number)
        if phone != instance.phone_number:
            validated_data['normalized_phone'] = self._normalize_phone(phone)
        if 'website' in validated_data:
            self._apply_website_type(validated_data)
        return super().update(instance, validated_data)