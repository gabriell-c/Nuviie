from rest_framework import serializers

from .models import ScoringCondition, ScoringRule


class ScoringConditionSerializer(serializers.ModelSerializer):
    field_label = serializers.SerializerMethodField()

    class Meta:
        model = ScoringCondition
        fields = [
            'id',
            'field_path',
            'field_label',
            'operator',
            'value',
            'sort_order',
        ]
        read_only_fields = ['id', 'field_label']

    def get_field_label(self, obj):
        from .engine import FIELD_REGISTRY_MAP
        meta = FIELD_REGISTRY_MAP.get(obj.field_path, {})
        return meta.get('label', obj.field_path)


class ScoringRuleSerializer(serializers.ModelSerializer):
    conditions = ScoringConditionSerializer(many=True)
    condition_count = serializers.SerializerMethodField()
    points_display = serializers.SerializerMethodField()
    scope_display = serializers.CharField(source='get_scope_display', read_only=True)

    class Meta:
        model = ScoringRule
        fields = [
            'id',
            'name',
            'description',
            'points',
            'points_display',
            'priority',
            'is_active',
            'match_mode',
            'scope',
            'scope_display',
            'conditions',
            'condition_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'condition_count',
            'points_display', 'scope_display',
        ]

    def get_condition_count(self, obj):
        return obj.conditions.count()

    def get_points_display(self, obj):
        sign = '+' if obj.points >= 0 else ''
        return f'{sign}{obj.points}'

    def create(self, validated_data):
        conditions_data = validated_data.pop('conditions', [])
        rule = ScoringRule.objects.create(**validated_data)
        for idx, cond_data in enumerate(conditions_data):
            cond_data.setdefault('sort_order', idx)
            ScoringCondition.objects.create(rule=rule, **cond_data)
        return rule

    def update(self, instance, validated_data):
        conditions_data = validated_data.pop('conditions', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if conditions_data is not None:
            instance.conditions.all().delete()
            for idx, cond_data in enumerate(conditions_data):
                cond_data.setdefault('sort_order', idx)
                ScoringCondition.objects.create(rule=instance, **cond_data)
        return instance
