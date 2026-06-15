from django.db import models
from django.conf import settings

class ContractTemplate(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contract_templates')
    name = models.CharField(max_length=255)
    pdf_file = models.FileField(upload_to='contract_templates/')
    detected_fields = models.JSONField(default=list, help_text="List of placeholder keys detected in the PDF (e.g. ['nome', 'cnpj'])")
    structure = models.JSONField(default=dict, blank=True, help_text="Segmented blocks: static vs variable")
    field_schema = models.JSONField(default=list, blank=True, help_text="Form field definitions for the template")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class GeneratedContract(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='generated_contracts')
    template = models.ForeignKey(ContractTemplate, on_delete=models.SET_NULL, null=True, related_name='generations')
    name = models.CharField(max_length=255)
    filled_data = models.JSONField(default=dict)
    pdf_file = models.FileField(upload_to='generated_contracts/')
    lead = models.ForeignKey(
        'leads.Lead', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='contracts',
    )
    client_name = models.CharField(max_length=255, blank=True, default='')
    payment_plan = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} (Gerado em {self.created_at.strftime('%d/%m/%Y')})"

    def save(self, *args, **kwargs):
        if not self.client_name and self.filled_data:
            self.client_name = (self.filled_data.get('nome_cliente') or '').strip()
        super().save(*args, **kwargs)
