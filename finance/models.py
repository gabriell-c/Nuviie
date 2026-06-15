from django.conf import settings
from django.db import models


class FinanceCategory(models.Model):
    TYPE_CHOICES = [
        ('income', 'Entrada'),
        ('expense', 'Despesa'),
    ]

    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    color = models.CharField(max_length=7, default='#6366f1')
    icon = models.CharField(max_length=50, default='fa-circle')
    icon_svg = models.TextField(blank=True, default='', help_text='SVG inline opcional')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category_type', 'name']
        verbose_name_plural = 'Finance categories'

    def __str__(self):
        return f'{self.name} ({self.get_category_type_display()})'


class FinanceEntry(models.Model):
    ENTRY_TYPE_CHOICES = [
        ('income', 'Entrada'),
        ('expense', 'Despesa'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('confirmed', 'Confirmado'),
        ('cancelled', 'Cancelado'),
    ]
    ATTACHMENT_KIND_CHOICES = [
        ('none', 'Nenhum'),
        ('receipt', 'Comprovante'),
        ('statement', 'Extrato'),
    ]
    SOURCE_CHOICES = [
        ('manual', 'Manual'),
        ('contract_auto', 'Contrato automático'),
        ('status_trigger', 'Gatilho de status'),
        ('recurring', 'Recorrente'),
    ]

    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    category = models.ForeignKey(
        FinanceCategory, on_delete=models.PROTECT, related_name='entries',
    )
    lead = models.ForeignKey(
        'leads.Lead', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='finance_entries',
    )
    contract = models.ForeignKey(
        'contracts.GeneratedContract', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='finance_entries',
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    attachment = models.FileField(upload_to='finance_attachments/', blank=True, null=True)
    attachment_kind = models.CharField(
        max_length=12, choices=ATTACHMENT_KIND_CHOICES, default='none',
    )
    is_recurring = models.BooleanField(default=False)
    recurrence_rule = models.JSONField(null=True, blank=True)
    parent_recurring = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='occurrences',
    )
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='manual')
    payment_plan_key = models.CharField(
        max_length=80, blank=True, default='',
        help_text='Chave idempotente do plano (ex: metade_2, parcela_3)',
    )
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='finance_entries_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['entry_type', 'date']),
            models.Index(fields=['status', 'due_date']),
        ]

    def __str__(self):
        return f'{self.title} — R$ {self.amount}'
