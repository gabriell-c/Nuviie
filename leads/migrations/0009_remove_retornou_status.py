from django.db import migrations, models


def migrate_retornou_to_contatado(apps, schema_editor):
    Lead = apps.get_model('leads', 'Lead')
    Lead.objects.filter(status='retornou').update(status='contatado')


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0008_alter_lead_id_alter_leadnote_id'),
    ]

    operations = [
        migrations.RunPython(migrate_retornou_to_contatado, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='lead',
            name='status',
            field=models.CharField(
                choices=[
                    ('novo', 'Novo Lead'),
                    ('contatado', 'Contatado'),
                    ('negociacao', 'Em Negociação'),
                    ('fechado', 'Em Produção'),
                    ('finalizado', 'Projeto Entregue'),
                    ('perdido', 'Perdido'),
                ],
                default='novo',
                max_length=20,
            ),
        ),
    ]
