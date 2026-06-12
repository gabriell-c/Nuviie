"""Recalcula pontuação de todos os leads após seed das regras."""

from django.db import migrations


def recalculate_leads(apps, schema_editor):
    from lead_scoring.recalculate import recalculate_all_leads

    recalculate_all_leads()


class Migration(migrations.Migration):

    dependencies = [
        ('lead_scoring', '0002_seed_default_rules'),
    ]

    operations = [
        migrations.RunPython(recalculate_leads, migrations.RunPython.noop),
    ]
