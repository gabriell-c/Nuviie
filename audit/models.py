from django.db import models
from django.conf import settings


class ActivityLog(models.Model):
    ACTION_CHOICES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('register', 'Cadastro'),
        ('face_register', 'Cadastro facial'),
        ('lead_create', 'Lead criado'),
        ('lead_update', 'Lead atualizado'),
        ('lead_delete', 'Lead excluído'),
        ('lead_bulk_delete', 'Leads excluídos em massa'),
        ('lead_delete_all', 'Todos os leads excluídos'),
        ('lead_import', 'Importação de leads'),
        ('lead_export', 'Exportação de leads'),
        ('instagram_scrape', 'Extração Instagram'),
        ('contract_template_upload', 'Template de contrato enviado'),
        ('contract_template_delete', 'Template excluído'),
        ('contract_generate', 'Contrato gerado'),
        ('contract_download', 'Contrato baixado'),
        ('contract_delete', 'Contrato excluído'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    entity_type = models.CharField(max_length=50, blank=True, null=True)
    entity_id = models.CharField(max_length=64, blank=True, null=True)
    description = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['action']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        who = self.user.username if self.user else 'Sistema'
        return f'{who} — {self.get_action_display()} — {self.created_at:%d/%m/%Y %H:%M}'
