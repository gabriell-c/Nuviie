from django.db import models


class ScoringRule(models.Model):
    MATCH_MODE_CHOICES = [
        ('all', 'Todas as condições'),
        ('any', 'Qualquer condição'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    points = models.IntegerField(help_text='Pontos somados (ou subtraídos se negativo) quando a regra bater.')
    priority = models.IntegerField(default=0, help_text='Ordem de exibição no breakdown (maior primeiro).')
    is_active = models.BooleanField(default=True)
    match_mode = models.CharField(max_length=3, choices=MATCH_MODE_CHOICES, default='all')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', 'name']
        verbose_name = 'Regra de pontuação'
        verbose_name_plural = 'Regras de pontuação'

    def __str__(self):
        sign = '+' if self.points >= 0 else ''
        return f'{self.name} ({sign}{self.points} pts)'


class ScoringCondition(models.Model):
    OPERATOR_CHOICES = [
        ('exists', 'Existe / preenchido'),
        ('empty', 'Vazio / ausente'),
        ('eq', 'Igual a'),
        ('neq', 'Diferente de'),
        ('contains', 'Contém'),
        ('in', 'Está na lista'),
        ('not_in', 'Não está na lista'),
        ('gt', 'Maior que'),
        ('gte', 'Maior ou igual a'),
        ('lt', 'Menor que'),
        ('lte', 'Menor ou igual a'),
        ('between', 'Entre (min e max)'),
        ('is_true', 'É verdadeiro'),
        ('is_false', 'É falso'),
        ('json_count_gte', 'Quantidade JSON ≥'),
        ('json_count_lte', 'Quantidade JSON ≤'),
    ]

    rule = models.ForeignKey(
        ScoringRule,
        on_delete=models.CASCADE,
        related_name='conditions',
    )
    field_path = models.CharField(max_length=120)
    operator = models.CharField(max_length=20, choices=OPERATOR_CHOICES)
    value = models.JSONField(null=True, blank=True, default=None)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Condição de pontuação'
        verbose_name_plural = 'Condições de pontuação'

    def __str__(self):
        return f'{self.field_path} {self.operator}'
