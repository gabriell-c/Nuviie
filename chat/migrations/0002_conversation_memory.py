from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='memory_summary',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Resumo rolante das mensagens antigas, usado como memória de longo prazo do agente.',
            ),
        ),
        migrations.AddField(
            model_name='conversation',
            name='summary_until_id',
            field=models.PositiveIntegerField(
                default=0,
                help_text='ID da última mensagem já incluída no resumo de memória.',
            ),
        ),
    ]
