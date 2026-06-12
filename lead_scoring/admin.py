from django.contrib import admin

from .models import ScoringCondition, ScoringRule


class ScoringConditionInline(admin.TabularInline):
    model = ScoringCondition
    extra = 1


@admin.register(ScoringRule)
class ScoringRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'points', 'priority', 'is_active', 'match_mode', 'updated_at')
    list_filter = ('is_active', 'match_mode')
    search_fields = ('name', 'description')
    inlines = [ScoringConditionInline]


@admin.register(ScoringCondition)
class ScoringConditionAdmin(admin.ModelAdmin):
    list_display = ('rule', 'field_path', 'operator', 'value', 'sort_order')
    list_filter = ('operator', 'field_path')
