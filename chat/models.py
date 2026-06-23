from django.db import models
from django.conf import settings
from django.utils import timezone


class Conversation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversations'
    )
    title = models.CharField(max_length=255, default='Nova Conversa')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    # Modo da IA para esta conversa (toggle nuvem x local).
    AI_MODE_CHOICES = [
        ('default', 'Padrão do sistema'),
        ('cloud', 'Nuvem (GPT/Gemini/Groq)'),
        ('local', 'Local (Ollama)'),
    ]
    ai_mode = models.CharField(max_length=10, choices=AI_MODE_CHOICES, default='default')
    # Memória de longo prazo: resumo rolante das mensagens mais antigas.
    summary = models.TextField(blank=True, default='')
    summary_message_count = models.PositiveIntegerField(
        default=0,
        help_text='Quantas das mensagens mais antigas já estão consolidadas no resumo.',
    )

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user.email} — {self.title} ({self.created_at.strftime('%d/%m/%Y')})"

    def get_last_message(self):
        return self.messages.order_by('-created_at').first()


class Message(models.Model):
    ROLE_CHOICES = [
        ('user', 'Usuário'),
        ('assistant', 'Assistente'),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.role}] {self.content[:60]}..."
