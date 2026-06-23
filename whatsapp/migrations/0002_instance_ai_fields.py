from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='whatsappinstance',
            name='ai_autoreply_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Se ligado, a IA responde sozinha as mensagens recebidas neste número.',
                verbose_name='Resposta automática por IA',
            ),
        ),
        migrations.AddField(
            model_name='whatsappinstance',
            name='ai_mode',
            field=models.CharField(
                choices=[
                    ('default', 'Padrão do sistema'),
                    ('cloud', 'Nuvem (GPT/Gemini/Groq)'),
                    ('local', 'Local (Ollama)'),
                ],
                default='default',
                max_length=10,
                verbose_name='Modo da IA (nuvem x local)',
            ),
        ),
    ]
