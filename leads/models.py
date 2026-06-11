from django.db import models
from django.conf import settings


class Lead(models.Model):
    STATUS_CHOICES = [
        ('novo', 'Novo Lead'),
        ('contatado', 'Contatado'),
        ('negociacao', 'Em Negociação'),
        ('retornou', 'Retornou'),
        ('fechado', 'Fechado (Ganho)'),
        ('perdido', 'Perdido'),
    ]

    SOURCE_CHOICES = [
        ('google_maps', 'Google Maps Scraper'),
        ('instagram', 'Instagram Scraper'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='leads')
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=150, blank=True, null=True)
    city = models.CharField(max_length=150, blank=True, null=True)

    # Contato
    phone_number = models.CharField(max_length=50, blank=True, null=True)
    normalized_phone = models.CharField(max_length=30, blank=True, null=True)
    website = models.URLField(max_length=500, blank=True, null=True)

    # Redes sociais
    instagram = models.CharField(max_length=255, blank=True, null=True)
    facebook = models.URLField(max_length=500, blank=True, null=True)
    youtube = models.URLField(max_length=500, blank=True, null=True)
    twitter = models.URLField(max_length=500, blank=True, null=True)
    linkedin = models.URLField(max_length=500, blank=True, null=True)

    # ✅ NOVO: tipo real do link de "site" detectado
    WEBSITE_TYPE_CHOICES = [
        ('website', 'Site próprio'),
        ('instagram', 'Link Instagram'),
        ('whatsapp', 'Link WhatsApp'),
        ('facebook', 'Link Facebook'),
        ('youtube', 'Link YouTube'),
        ('linktree', 'Linktree / Bio link'),
        ('other_social', 'Outra rede social'),
    ]
    website_detected_type = models.CharField(
        max_length=20, choices=WEBSITE_TYPE_CHOICES,
        blank=True, null=True,
        verbose_name='Tipo real do link de site'
    )

    # Perfil
    bio = models.TextField(blank=True, null=True)
    profile_picture_url = models.URLField(max_length=1000, blank=True, null=True)

    # Endereço e avaliações (Google Maps)
    address = models.CharField(max_length=500, blank=True, null=True)
    rating = models.FloatField(blank=True, null=True)
    review_count = models.IntegerField(default=0)

    # ✅ NOVO: avaliações recentes (JSON, máx 10) e horários de funcionamento
    recent_reviews = models.JSONField(
        blank=True, null=True,
        verbose_name='Avaliações recentes (JSON)',
        help_text='Lista das últimas 10 avaliações do Google Maps'
    )
    business_hours = models.JSONField(
        blank=True, null=True,
        verbose_name='Horários de funcionamento (JSON)',
        help_text='Dict com dias da semana e horários'
    )

    # Link direto Google Maps / Google Meu Negócio
    maps_url = models.URLField(max_length=1000, blank=True, null=True, verbose_name='Link Google Maps')

    # ✅ NOVO: link curto compartilhável (share.google / maps.app.goo.gl)
    maps_share_url = models.URLField(
        max_length=500, blank=True, null=True,
        verbose_name='Link curto Google (share.google)'
    )

    # ✅ v10: campos extras do box do Google Maps
    price_range = models.CharField(
        max_length=10, blank=True, null=True,
        verbose_name='Faixa de preço ($, $$, $$$)',
        help_text='Ex: $, $$, $$$, $$$$'
    )
    plus_code = models.CharField(
        max_length=20, blank=True, null=True,
        verbose_name='Plus Code',
        help_text='Ex: 5HMG+V3 Ribeirão Preto'
    )
    amenities = models.JSONField(
        blank=True, null=True,
        verbose_name='Amenidades / Atributos',
        help_text='Lista de atributos do lugar: Wi-Fi, estacionamento, acessibilidade etc.'
    )
    total_photos = models.IntegerField(
        blank=True, null=True,
        verbose_name='Total de fotos no Maps'
    )

    # Status CRM
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='novo')
    quality_score = models.IntegerField(default=0)
    is_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'normalized_phone']),
            models.Index(fields=['user', 'name']),
            models.Index(fields=['status']),
        ]

    def get_whatsapp_link(self):
        if self.normalized_phone:
            return f"https://wa.me/{self.normalized_phone}"
        return None

    def get_maps_link(self):
        """Retorna o melhor link disponível: share_url > maps_url."""
        return self.maps_share_url or self.maps_url or None

    def calculate_quality(self):
        score = 0
        if self.website and self.website_detected_type == 'website':
            score += 15
        elif self.website and self.website_detected_type in (None, 'website'):
            score += 15
        elif self.website_detected_type in ('linktree', 'whatsapp', 'facebook', 'youtube', 'linkedin'):
            score += 8
        if self.normalized_phone:
            score += 20
        if self.instagram:
            score += 10
        if self.facebook:
            score += 5
        if self.youtube:
            score += 5
        if self.twitter:
            score += 5
        if self.linkedin:
            score += 5
        if self.category:
            score += 10
        if self.address or self.rating:
            score += 10
        if self.maps_url or self.maps_share_url:
            score += 10
        if self.profile_picture_url:
            score += 5
        if self.amenities:
            score += 3
        if self.plus_code:
            score += 2

        post_count = self.total_photos
        if post_count is None and isinstance(self.amenities, dict):
            post_count = self.amenities.get('post_count')
        if post_count:
            post_count = int(post_count)
            if post_count >= 51:
                score += 8
            elif post_count >= 11:
                score += 5
            elif post_count >= 1:
                score += 3

        latest_post_at = None
        if isinstance(self.amenities, dict):
            latest_post_at = self.amenities.get('latest_post_at')
        if latest_post_at:
            from datetime import datetime, timezone
            try:
                ts = int(latest_post_at)
                days_ago = (
                    datetime.now(timezone.utc)
                    - datetime.fromtimestamp(ts, tz=timezone.utc)
                ).days
                if days_ago <= 30:
                    score += 10
                elif days_ago <= 90:
                    score += 5
                elif days_ago <= 180:
                    score += 2
            except (TypeError, ValueError, OSError):
                pass

        if self.is_verified:
            score += 5

        return min(score, 100)

    def save(self, *args, **kwargs):
        self.quality_score = self.calculate_quality()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


class LeadNote(models.Model):
    ACTION_CHOICES = [
        ('creation', 'Criação'),
        ('edit', 'Edição'),
        ('status_change', 'Alteração de Status'),
        ('note', 'Observação Interna'),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='notes')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    note = models.TextField()
    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES, default='note')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return (
            f"{self.get_action_type_display()} por "
            f"{self.user.first_name or self.user.username} "
            f"em {self.created_at.strftime('%d/%m/%Y %H:%M')}"
        )