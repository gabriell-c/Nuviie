from django.conf import settings
from django.db import models


class SiteAuditReport(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pendente'),
        (STATUS_RUNNING, 'Em execução'),
        (STATUS_COMPLETED, 'Concluída'),
        (STATUS_FAILED, 'Falhou'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='site_audits',
    )
    lead = models.ForeignKey(
        'leads.Lead',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='site_audits',
    )
    url = models.URLField(max_length=500)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    scores = models.JSONField(default=dict, blank=True)
    core_web_vitals = models.JSONField(default=dict, blank=True)
    recommendations = models.JSONField(default=dict, blank=True)
    summary = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Audit #{self.pk} — {self.url} ({self.status})'


class SiteAuditVisualAsset(models.Model):
    KIND_CROP = 'crop'
    KIND_SCREENSHOT = 'screenshot'
    KIND_CHOICES = [
        (KIND_CROP, 'Crop'),
        (KIND_SCREENSHOT, 'Screenshot'),
    ]

    report = models.ForeignKey(
        SiteAuditReport,
        on_delete=models.CASCADE,
        related_name='visual_assets',
    )
    asset_id = models.CharField(max_length=32, db_index=True)
    file = models.CharField(max_length=500)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_CROP)
    audit_id = models.CharField(max_length=120, blank=True)
    strategy = models.CharField(max_length=20, blank=True)
    element_index = models.PositiveSmallIntegerField(null=True, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f'Visual {self.asset_id} — report #{self.report_id}'
