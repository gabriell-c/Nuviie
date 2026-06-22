"""Adiciona a regra de 'Oportunidade' ao score oficial e recalcula os leads."""

from django.db import migrations

RULE_NAME = 'Oportunidade (sem site + contato)'


def seed_opportunity_rule(apps, schema_editor):
    ScoringRule = apps.get_model('lead_scoring', 'ScoringRule')
    ScoringCondition = apps.get_model('lead_scoring', 'ScoringCondition')

    if ScoringRule.objects.filter(name=RULE_NAME).exists():
        return

    rule = ScoringRule.objects.create(
        name=RULE_NAME,
        description=(
            'Lead quente para a agência: não tem site próprio, tem um canal de '
            'contato (telefone/WhatsApp ou e-mail) e está ativo ou é conta '
            'profissional. Forte sinal de venda.'
        ),
        points=25,
        priority=110,
        is_active=True,
        match_mode='all',
        scope='global',
    )
    ScoringCondition.objects.create(
        rule=rule,
        field_path='is_opportunity',
        operator='is_true',
        value=None,
        sort_order=0,
    )


def unseed_opportunity_rule(apps, schema_editor):
    ScoringRule = apps.get_model('lead_scoring', 'ScoringRule')
    ScoringRule.objects.filter(name=RULE_NAME).delete()


def recalculate_leads(apps, schema_editor):
    from lead_scoring.recalculate import recalculate_all_leads

    recalculate_all_leads()


class Migration(migrations.Migration):

    dependencies = [
        ('lead_scoring', '0004_scoringrule_scope'),
        ('leads', '0010_lead_email'),
    ]

    operations = [
        migrations.RunPython(seed_opportunity_rule, unseed_opportunity_rule),
        migrations.RunPython(recalculate_leads, migrations.RunPython.noop),
    ]
