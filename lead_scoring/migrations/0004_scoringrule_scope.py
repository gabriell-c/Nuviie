"""Adiciona escopo às regras e classifica regras seed existentes."""

from django.db import migrations, models

SCOPE_BY_RULE_NAME = {
    'Endereço ou avaliação Maps': 'google_maps',
    'Link Google Maps': 'google_maps',
    'Amenidades / dados extras': 'google_maps',
    'Plus Code': 'google_maps',
    '51+ publicações': 'instagram',
    '11–50 publicações': 'instagram',
    '1–10 publicações': 'instagram',
    'Postou nos últimos 30 dias': 'instagram',
    'Postou nos últimos 90 dias': 'instagram',
    'Postou nos últimos 180 dias': 'instagram',
    'Perfil verificado': 'instagram',
}


def classify_rule_scopes(apps, schema_editor):
    ScoringRule = apps.get_model('lead_scoring', 'ScoringRule')
    for rule in ScoringRule.objects.all():
        scope = SCOPE_BY_RULE_NAME.get(rule.name, 'global')
        if rule.scope != scope:
            rule.scope = scope
            rule.save(update_fields=['scope'])


class Migration(migrations.Migration):

    dependencies = [
        ('lead_scoring', '0003_recalculate_leads'),
    ]

    operations = [
        migrations.AddField(
            model_name='scoringrule',
            name='scope',
            field=models.CharField(
                choices=[
                    ('global', 'Geral'),
                    ('instagram', 'Instagram'),
                    ('google_maps', 'Google Maps'),
                ],
                default='global',
                help_text='Regras Instagram/Google Maps só avaliam leads dessa origem.',
                max_length=20,
            ),
        ),
        migrations.RunPython(classify_rule_scopes, migrations.RunPython.noop),
    ]
