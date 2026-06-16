from django.contrib import admin
from .models import SiteAuditReport, SiteAuditVisualAsset


@admin.register(SiteAuditReport)
class SiteAuditReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'url', 'user', 'lead', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('url',)


@admin.register(SiteAuditVisualAsset)
class SiteAuditVisualAssetAdmin(admin.ModelAdmin):
    list_display = ('asset_id', 'report', 'kind', 'strategy', 'expires_at')
    list_filter = ('kind', 'strategy')
