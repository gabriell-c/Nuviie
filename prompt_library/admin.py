from django.contrib import admin

from .models import Prompt, PromptCategory


@admin.register(PromptCategory)
class PromptCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'color', 'updated_at')
    search_fields = ('name',)


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'updated_at')
    list_filter = ('category',)
    search_fields = ('title', 'content')
