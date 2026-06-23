from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0002_conversation_summary'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='ai_mode',
            field=models.CharField(
                choices=[
                    ('default', 'Padrão do sistema'),
                    ('cloud', 'Nuvem (GPT/Gemini/Groq)'),
                    ('local', 'Local (Ollama)'),
                ],
                default='default',
                max_length=10,
            ),
        ),
    ]
