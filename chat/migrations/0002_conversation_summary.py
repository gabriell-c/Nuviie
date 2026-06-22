from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='summary',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='conversation',
            name='summary_message_count',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Quantas das mensagens mais antigas já estão consolidadas no resumo.',
            ),
        ),
    ]
