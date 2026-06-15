from rest_framework import serializers

from .models import FinanceCategory, FinanceEntry


class FinanceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = FinanceCategory
        fields = ['id', 'name', 'category_type', 'color', 'icon', 'created_at']


class FinanceEntrySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_color = serializers.CharField(source='category.color', read_only=True)
    lead_name = serializers.CharField(source='lead.name', read_only=True, allow_null=True)
    contract_name = serializers.CharField(source='contract.client_name', read_only=True, allow_null=True)
    attachment_url = serializers.SerializerMethodField()

    class Meta:
        model = FinanceEntry
        fields = [
            'id', 'entry_type', 'title', 'amount', 'date', 'due_date',
            'category', 'category_name', 'category_color',
            'lead', 'lead_name', 'contract', 'contract_name',
            'status', 'attachment', 'attachment_url', 'attachment_kind',
            'is_recurring', 'recurrence_rule', 'parent_recurring',
            'source', 'payment_plan_key', 'notes',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'payment_plan_key']

    def get_attachment_url(self, obj):
        if not obj.attachment:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.attachment.url)
        return obj.attachment.url

    def validate(self, attrs):
        entry_type = attrs.get('entry_type') or getattr(self.instance, 'entry_type', None)
        kind = attrs.get('attachment_kind') or getattr(self.instance, 'attachment_kind', 'none')
        if kind == 'statement' and entry_type == 'income':
            raise serializers.ValidationError(
                {'attachment_kind': 'Extrato bancário só é permitido em despesas.'},
            )
        if kind == 'receipt' and entry_type == 'expense':
            raise serializers.ValidationError(
                {'attachment_kind': 'Comprovante de cliente só é permitido em entradas.'},
            )
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data.setdefault('created_by', request.user)
        return super().create(validated_data)
