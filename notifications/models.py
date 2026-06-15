from django.conf import settings
from django.db import models


class Notification(models.Model):
    LEVEL_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Aviso'),
        ('danger', 'Urgente'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='notifications',
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='info')
    lead = models.ForeignKey(
        'leads.Lead', on_delete=models.CASCADE, null=True, blank=True,
        related_name='notifications',
    )
    trigger_date = models.DateField(null=True, blank=True)
    dedupe_key = models.CharField(max_length=120, blank=True, default='')
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'read_at']),
            models.Index(fields=['dedupe_key']),
        ]

    def __str__(self):
        return self.title
