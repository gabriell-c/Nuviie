from django.db import models


class PromptCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    color = models.CharField(max_length=7, default='#6366f1')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Categoria de prompt'
        verbose_name_plural = 'Categorias de prompt'

    def __str__(self):
        return self.name


class Prompt(models.Model):
    category = models.ForeignKey(
        PromptCategory,
        on_delete=models.PROTECT,
        related_name='prompts',
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Prompt'
        verbose_name_plural = 'Prompts'

    def __str__(self):
        return self.title
