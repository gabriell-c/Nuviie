from django.conf import settings
from django.db import models


class WhatsAppInstance(models.Model):
    """Um número de WhatsApp conectado via Evolution API (uma instância = um número)."""

    STATUS_CHOICES = [
        ('created', 'Criada'),
        ('connecting', 'Conectando (aguardando QR)'),
        ('connected', 'Conectada'),
        ('disconnected', 'Desconectada'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='whatsapp_instances',
    )
    name = models.CharField(
        max_length=120,
        verbose_name='Nome amigável',
        help_text='Ex: Comercial, Suporte',
    )
    instance_name = models.CharField(
        max_length=120, unique=True,
        verbose_name='Instância (Evolution)',
        help_text='Identificador da instância no Evolution API',
    )
    phone_number = models.CharField(
        max_length=30, blank=True, default='',
        verbose_name='Número (somente dígitos)',
    )
    # Sobrescreve as credenciais globais do settings, se preenchido.
    api_url = models.URLField(max_length=500, blank=True, default='')
    api_key = models.CharField(max_length=255, blank=True, default='')

    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='created')
    is_default = models.BooleanField(
        default=False,
        verbose_name='Número padrão para envios',
    )
    is_active = models.BooleanField(default=True)

    # ── Atendente IA por número ──────────────────────────────────────────────
    AI_MODE_CHOICES = [
        ('default', 'Padrão do sistema'),
        ('cloud', 'Nuvem (GPT/Gemini/Groq)'),
        ('local', 'Local (Ollama)'),
    ]
    ai_autoreply_enabled = models.BooleanField(
        default=False,
        verbose_name='Resposta automática por IA',
        help_text='Se ligado, a IA responde sozinha as mensagens recebidas neste número.',
    )
    ai_mode = models.CharField(
        max_length=10, choices=AI_MODE_CHOICES, default='default',
        verbose_name='Modo da IA (nuvem x local)',
    )

    last_qr_base64 = models.TextField(blank=True, default='')
    last_connected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', 'name']
        verbose_name = 'Instância WhatsApp'
        verbose_name_plural = 'Instâncias WhatsApp'

    def __str__(self):
        return f"{self.name} ({self.instance_name})"

    @property
    def is_connected(self):
        return self.status == 'connected'


class WhatsAppMessage(models.Model):
    """Histórico de mensagens enviadas/recebidas, vinculadas a um lead quando possível."""

    DIRECTION_CHOICES = [
        ('out', 'Enviada'),
        ('in', 'Recebida'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('sent', 'Enviada'),
        ('delivered', 'Entregue'),
        ('read', 'Lida'),
        ('received', 'Recebida'),
        ('failed', 'Falhou'),
    ]
    TYPE_CHOICES = [
        ('text', 'Texto'),
        ('image', 'Imagem'),
        ('video', 'Vídeo'),
        ('audio', 'Áudio'),
        ('document', 'Documento'),
        ('sticker', 'Figurinha'),
        ('location', 'Localização'),
        ('contact', 'Contato'),
        ('other', 'Outro'),
    ]

    instance = models.ForeignKey(
        WhatsAppInstance, on_delete=models.CASCADE,
        related_name='messages', null=True, blank=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='whatsapp_messages',
    )
    lead = models.ForeignKey(
        'leads.Lead', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='whatsapp_messages',
    )

    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    remote_jid = models.CharField(max_length=120, blank=True, default='')
    phone = models.CharField(max_length=30, blank=True, default='', db_index=True)
    contact_name = models.CharField(max_length=255, blank=True, default='')

    message_type = models.CharField(max_length=15, choices=TYPE_CHOICES, default='text')
    text = models.TextField(blank=True, default='')
    media_url = models.URLField(max_length=1000, blank=True, default='')

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    evolution_id = models.CharField(max_length=120, blank=True, default='', db_index=True)
    error = models.TextField(blank=True, default='')
    raw = models.JSONField(null=True, blank=True)

    timestamp = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp', 'created_at']
        indexes = [
            models.Index(fields=['user', 'phone']),
            models.Index(fields=['lead', 'created_at']),
        ]
        verbose_name = 'Mensagem WhatsApp'
        verbose_name_plural = 'Mensagens WhatsApp'

    def __str__(self):
        arrow = '→' if self.direction == 'out' else '←'
        return f"{arrow} {self.phone}: {self.text[:40]}"
