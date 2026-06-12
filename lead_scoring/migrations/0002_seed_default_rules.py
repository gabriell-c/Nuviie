"""Seed regras padrão equivalentes à pontuação hardcoded anterior."""

from django.db import migrations


def _create_rule(ScoringRule, ScoringCondition, name, points, priority, match_mode, conditions):
    rule = ScoringRule.objects.create(
        name=name,
        points=points,
        priority=priority,
        is_active=True,
        match_mode=match_mode,
    )
    for idx, cond in enumerate(conditions):
        ScoringCondition.objects.create(
            rule=rule,
            field_path=cond['field_path'],
            operator=cond['operator'],
            value=cond.get('value'),
            sort_order=idx,
        )
    return rule


def seed_default_rules(apps, schema_editor):
    ScoringRule = apps.get_model('lead_scoring', 'ScoringRule')
    ScoringCondition = apps.get_model('lead_scoring', 'ScoringCondition')

    if ScoringRule.objects.exists():
        return

    _create_rule(
        ScoringRule, ScoringCondition,
        'Site próprio', 15, 100, 'all',
        [{'field_path': 'website_detected_type', 'operator': 'eq', 'value': 'website'}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'Link de bio (Linktree/redes)', 8, 95, 'all',
        [{'field_path': 'website_detected_type', 'operator': 'in',
          'value': ['linktree', 'whatsapp', 'facebook', 'youtube', 'linkedin']}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'Telefone / WhatsApp', 20, 90, 'all',
        [{'field_path': 'normalized_phone', 'operator': 'exists', 'value': None}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'Instagram', 10, 85, 'all',
        [{'field_path': 'instagram', 'operator': 'exists', 'value': None}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'Facebook', 5, 80, 'all',
        [{'field_path': 'facebook', 'operator': 'exists', 'value': None}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'YouTube', 5, 79, 'all',
        [{'field_path': 'youtube', 'operator': 'exists', 'value': None}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'Twitter / X', 5, 78, 'all',
        [{'field_path': 'twitter', 'operator': 'exists', 'value': None}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'LinkedIn', 5, 77, 'all',
        [{'field_path': 'linkedin', 'operator': 'exists', 'value': None}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'Categoria definida', 10, 75, 'all',
        [{'field_path': 'category', 'operator': 'exists', 'value': None}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'Endereço ou avaliação Maps', 10, 70, 'any',
        [
            {'field_path': 'address', 'operator': 'exists', 'value': None},
            {'field_path': 'rating', 'operator': 'exists', 'value': None},
        ],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'Link Google Maps', 10, 65, 'any',
        [
            {'field_path': 'maps_url', 'operator': 'exists', 'value': None},
            {'field_path': 'maps_share_url', 'operator': 'exists', 'value': None},
        ],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'Foto de perfil', 5, 60, 'all',
        [{'field_path': 'profile_picture_url', 'operator': 'exists', 'value': None}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'Amenidades / dados extras', 3, 55, 'all',
        [{'field_path': 'amenities', 'operator': 'exists', 'value': None}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'Plus Code', 2, 50, 'all',
        [{'field_path': 'plus_code', 'operator': 'exists', 'value': None}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        '51+ publicações', 8, 45, 'all',
        [{'field_path': 'effective_post_count', 'operator': 'gte', 'value': 51}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        '11–50 publicações', 5, 44, 'all',
        [{'field_path': 'effective_post_count', 'operator': 'between', 'value': {'min': 11, 'max': 50}}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        '1–10 publicações', 3, 43, 'all',
        [{'field_path': 'effective_post_count', 'operator': 'between', 'value': {'min': 1, 'max': 10}}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'Postou nos últimos 30 dias', 10, 40, 'all',
        [{'field_path': 'days_since_latest_post', 'operator': 'lte', 'value': 30}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'Postou nos últimos 90 dias', 5, 39, 'all',
        [{'field_path': 'days_since_latest_post', 'operator': 'lte', 'value': 90}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'Postou nos últimos 180 dias', 2, 38, 'all',
        [{'field_path': 'days_since_latest_post', 'operator': 'lte', 'value': 180}],
    )
    _create_rule(
        ScoringRule, ScoringCondition,
        'Perfil verificado', 5, 35, 'all',
        [{'field_path': 'is_verified', 'operator': 'is_true', 'value': None}],
    )


def unseed_default_rules(apps, schema_editor):
    ScoringRule = apps.get_model('lead_scoring', 'ScoringRule')
    ScoringRule.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('lead_scoring', '0001_initial'),
        ('leads', '0006_lead_score_breakdown'),
    ]

    operations = [
        migrations.RunPython(seed_default_rules, unseed_default_rules),
    ]
