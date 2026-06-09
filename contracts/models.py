from django.db import models
from django.conf import settings

class ContractTemplate(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contract_templates')
    name = models.CharField(max_length=255)
    pdf_file = models.FileField(upload_to='contract_templates/')
    detected_fields = models.JSONField(default=list, help_text="List of placeholder keys detected in the PDF (e.g. ['nome', 'cnpj'])")
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} (Gerado em {self.created_at.strftime('%d/%m/%Y')})"
