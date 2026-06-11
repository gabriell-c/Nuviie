from rest_framework import serializers

from .models import Prompt, PromptCategory


class PromptCategorySerializer(serializers.ModelSerializer):
    prompt_count = serializers.SerializerMethodField()

    class Meta:
        model = PromptCategory
        fields = ['id', 'name', 'color', 'prompt_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at', 'prompt_count']

    def get_prompt_count(self, obj):
        return obj.prompts.count()


class PromptSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_color = serializers.CharField(source='category.color', read_only=True)

    class Meta:
        model = Prompt
        fields = [
            'id',
            'title',
            'content',
            'category',
            'category_name',
            'category_color',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'category_name', 'category_color']
