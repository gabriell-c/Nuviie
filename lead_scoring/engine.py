"""Motor de pontuação configurável para leads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

OPERATORS_BY_TYPE = {
    'text': ['exists', 'empty', 'eq', 'neq', 'contains', 'in', 'not_in'],
    'number': ['exists', 'empty', 'eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'between'],
    'boolean': ['exists', 'is_true', 'is_false'],
    'choice': ['exists', 'empty', 'eq', 'neq', 'in', 'not_in'],
    'json': ['exists', 'empty', 'json_count_gte', 'json_count_lte'],
}

FIELD_REGISTRY: list[dict[str, Any]] = [
    {'path': 'name', 'label': 'Nome', 'type': 'text'},
    {'path': 'category', 'label': 'Categoria / nicho', 'type': 'text'},
    {'path': 'city', 'label': 'Cidade', 'type': 'text'},
    {'path': 'phone_number', 'label': 'Telefone', 'type': 'text'},
    {'path': 'normalized_phone', 'label': 'Telefone normalizado (WhatsApp)', 'type': 'text'},
    {'path': 'website', 'label': 'Website / link principal', 'type': 'text'},
    {'path': 'website_detected_type', 'label': 'Tipo do link de site', 'type': 'choice',
     'choices': [
         ('website', 'Site próprio'),
         ('instagram', 'Link Instagram'),
         ('whatsapp', 'Link WhatsApp'),
         ('facebook', 'Link Facebook'),
         ('youtube', 'Link YouTube'),
         ('linktree', 'Linktree / Bio link'),
         ('other_social', 'Outra rede social'),
     ]},
    {'path': 'instagram', 'label': 'Instagram (@handle)', 'type': 'text'},
    {'path': 'facebook', 'label': 'Facebook URL', 'type': 'text'},
    {'path': 'youtube', 'label': 'YouTube URL', 'type': 'text'},
    {'path': 'twitter', 'label': 'Twitter / X URL', 'type': 'text'},
    {'path': 'linkedin', 'label': 'LinkedIn URL', 'type': 'text'},
    {'path': 'bio', 'label': 'Biografia / descrição', 'type': 'text'},
    {'path': 'profile_picture_url', 'label': 'Foto de perfil (URL)', 'type': 'text'},
    {'path': 'address', 'label': 'Endereço', 'type': 'text'},
    {'path': 'rating', 'label': 'Nota Google Maps', 'type': 'number'},
    {'path': 'review_count', 'label': 'Quantidade de avaliações', 'type': 'number'},
    {'path': 'recent_reviews', 'label': 'Avaliações recentes (JSON)', 'type': 'json'},
    {'path': 'recent_reviews_count', 'label': 'Qtd. avaliações recentes', 'type': 'number'},
    {'path': 'business_hours', 'label': 'Horários de funcionamento (JSON)', 'type': 'json'},
    {'path': 'maps_url', 'label': 'Link Google Maps', 'type': 'text'},
    {'path': 'maps_share_url', 'label': 'Link curto Google Maps', 'type': 'text'},
    {'path': 'price_range', 'label': 'Faixa de preço ($–$$$$)', 'type': 'text'},
    {'path': 'plus_code', 'label': 'Plus Code', 'type': 'text'},
    {'path': 'amenities', 'label': 'Amenidades / dados extras (JSON)', 'type': 'json'},
    {'path': 'total_photos', 'label': 'Total de fotos / publicações', 'type': 'number'},
    {'path': 'effective_post_count', 'label': 'Publicações (Maps ou Instagram)', 'type': 'number'},
    {'path': 'amenities.follower_count', 'label': 'Seguidores Instagram', 'type': 'number'},
    {'path': 'amenities.post_count', 'label': 'Publicações (amenities)', 'type': 'number'},
    {'path': 'amenities.latest_post_at', 'label': 'Timestamp última postagem', 'type': 'number'},
    {'path': 'days_since_latest_post', 'label': 'Dias desde última postagem', 'type': 'number'},
    {'path': 'amenities.recent_posts', 'label': 'Posts recentes (JSON)', 'type': 'json'},
    {'path': 'amenities.recent_reels', 'label': 'Reels recentes (JSON)', 'type': 'json'},
    {'path': 'source', 'label': 'Origem do lead', 'type': 'choice',
     'choices': [('google_maps', 'Google Maps'), ('instagram', 'Instagram Scraper'), ('manual', 'Manual')]},
    {'path': 'status', 'label': 'Status CRM', 'type': 'choice',
     'choices': [
         ('novo', 'Novo Lead'),
         ('contatado', 'Contatado'),
         ('negociacao', 'Em Negociação'),
         ('fechado', 'Em Produção'),
         ('finalizado', 'Projeto Entregue'),
         ('perdido', 'Perdido'),
     ]},
    {'path': 'is_verified', 'label': 'Verificado (Instagram)', 'type': 'boolean'},
    {'path': 'amenities.is_business_account', 'label': 'Conta comercial/profissional', 'type': 'boolean'},
    {'path': 'amenities.engagement_rate', 'label': 'Taxa de engajamento (%)', 'type': 'number'},
    {'path': 'is_opportunity', 'label': 'Oportunidade (sem site + contato)', 'type': 'boolean'},
]

FIELD_REGISTRY_MAP = {item['path']: item for item in FIELD_REGISTRY}

SCOPE_LABELS = {
    'global': 'Geral',
    'instagram': 'Instagram',
    'google_maps': 'Google Maps',
}


def rule_applies_to_lead(rule, lead) -> bool:
    """Regras com escopo específico só avaliam leads da mesma origem."""
    scope = getattr(rule, 'scope', 'global') or 'global'
    if scope == 'global':
        return True
    if scope == 'instagram':
        return lead.source == 'instagram'
    if scope == 'google_maps':
        return lead.source == 'google_maps'
    return True


def get_field_registry() -> list[dict[str, Any]]:
    """Retorna registro de campos com operadores permitidos para a API/UI."""
    from .field_groups import field_group_for_path

    result = []
    for field in FIELD_REGISTRY:
        entry = {
            'path': field['path'],
            'label': field['label'],
            'type': field['type'],
            'group': field_group_for_path(field['path']),
            'operators': OPERATORS_BY_TYPE.get(field['type'], []),
        }
        if 'choices' in field:
            entry['choices'] = [{'value': v, 'label': lbl} for v, lbl in field['choices']]
        result.append(entry)
    return result


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ''
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _to_number(value: Any) -> float | None:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_length(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return len(value)
    return None


def _effective_post_count(lead) -> int | None:
    if lead.total_photos is not None:
        try:
            return int(lead.total_photos)
        except (TypeError, ValueError):
            pass
    amenities = lead.amenities if isinstance(lead.amenities, dict) else {}
    post_count = amenities.get('post_count')
    if post_count is not None:
        try:
            return int(post_count)
        except (TypeError, ValueError):
            pass
    return None


def _days_since_latest_post(lead) -> int | None:
    amenities = lead.amenities if isinstance(lead.amenities, dict) else {}
    latest_post_at = amenities.get('latest_post_at')
    if latest_post_at is None:
        return None
    try:
        ts = int(latest_post_at)
        return (
            datetime.now(timezone.utc)
            - datetime.fromtimestamp(ts, tz=timezone.utc)
        ).days
    except (TypeError, ValueError, OSError):
        return None


def _recent_reviews_count(lead) -> int | None:
    if isinstance(lead.recent_reviews, list):
        return len(lead.recent_reviews)
    return None


def is_opportunity(lead) -> bool:
    """Sinal de "lead quente": negócio ativo/comercial, com forma de contato e
    SEM site próprio (logo, candidato ideal para vender um site).

    Confia na flag pré-calculada pela extensão (amenities.is_opportunity) quando
    existir; caso contrário deriva server-side a partir dos campos disponíveis.
    """
    amenities = lead.amenities if isinstance(lead.amenities, dict) else {}

    flag = amenities.get('is_opportunity')
    if isinstance(flag, bool):
        return flag

    website_type = getattr(lead, 'website_detected_type', None)
    has_real_site = website_type == 'website'

    has_contact = bool(
        getattr(lead, 'normalized_phone', None)
        or getattr(lead, 'phone_number', None)
        or getattr(lead, 'email', None)
        or amenities.get('whatsapp_number')
    )

    is_professional = bool(
        amenities.get('is_business_account')
        or amenities.get('is_professional_account')
    )

    days = _days_since_latest_post(lead)
    is_active = days is not None and days <= 60

    return (not has_real_site) and has_contact and (is_professional or is_active)


def get_field_value(lead, field_path: str) -> Any:
    """Resolve valor de um campo do lead, incluindo paths derivados e aninhados."""
    if field_path == 'effective_post_count':
        return _effective_post_count(lead)
    if field_path == 'days_since_latest_post':
        return _days_since_latest_post(lead)
    if field_path == 'recent_reviews_count':
        return _recent_reviews_count(lead)
    if field_path == 'is_opportunity':
        return is_opportunity(lead)

    if '.' in field_path:
        root, nested = field_path.split('.', 1)
        root_value = getattr(lead, root, None)
        if not isinstance(root_value, dict):
            return None
        return root_value.get(nested)

    return getattr(lead, field_path, None)


def _format_value(value: Any) -> str:
    if value is None:
        return '(vazio)'
    if isinstance(value, bool):
        return 'sim' if value else 'não'
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def evaluate_condition(lead, condition) -> dict[str, Any]:
    """Avalia uma condição e retorna passed, actual, expected, reason."""
    field_path = condition.field_path
    operator = condition.operator
    expected = condition.value
    actual = get_field_value(lead, field_path)
    field_meta = FIELD_REGISTRY_MAP.get(field_path, {})
    field_label = field_meta.get('label', field_path)

    passed = False
    reason = ''

    if operator == 'exists':
        passed = not _is_empty(actual)
        reason = f'{field_label} está preenchido' if passed else f'{field_label} está vazio'
    elif operator == 'empty':
        passed = _is_empty(actual)
        reason = f'{field_label} está vazio' if passed else f'{field_label} está preenchido ({_format_value(actual)})'
    elif operator == 'is_true':
        passed = actual is True
        reason = f'{field_label} é verdadeiro' if passed else f'{field_label} não é verdadeiro ({_format_value(actual)})'
    elif operator == 'is_false':
        passed = actual is False or actual is None
        reason = f'{field_label} é falso ou ausente' if passed else f'{field_label} é verdadeiro'
    elif operator == 'contains':
        passed = not _is_empty(actual) and str(expected or '').lower() in str(actual).lower()
        reason = (
            f'{field_label} contém "{expected}"'
            if passed
            else f'{field_label} ({_format_value(actual)}) não contém "{expected}"'
        )
    elif operator == 'in':
        choices = expected if isinstance(expected, list) else [expected]
        passed = str(actual) in [str(c) for c in choices]
        reason = (
            f'{field_label} está em {choices}'
            if passed
            else f'{field_label} ({_format_value(actual)}) não está em {choices}'
        )
    elif operator == 'not_in':
        choices = expected if isinstance(expected, list) else [expected]
        passed = _is_empty(actual) or str(actual) not in [str(c) for c in choices]
        reason = (
            f'{field_label} não está em {choices}'
            if passed
            else f'{field_label} ({_format_value(actual)}) está em {choices}'
        )
    elif operator == 'between':
        num = _to_number(actual)
        if isinstance(expected, dict):
            min_val = _to_number(expected.get('min'))
            max_val = _to_number(expected.get('max'))
        elif isinstance(expected, (list, tuple)) and len(expected) >= 2:
            min_val = _to_number(expected[0])
            max_val = _to_number(expected[1])
        else:
            min_val = max_val = None
        passed = (
            num is not None
            and min_val is not None
            and max_val is not None
            and min_val <= num <= max_val
        )
        reason = (
            f'{field_label} ({_format_value(actual)}) está entre {min_val} e {max_val}'
            if passed
            else f'{field_label} ({_format_value(actual)}) fora de {min_val}–{max_val}'
        )
    elif operator in ('json_count_gte', 'json_count_lte'):
        length = _json_length(actual)
        threshold = _to_number(expected)
        if length is None or threshold is None:
            passed = False
            reason = f'{field_label} não é uma lista/dict válida'
        elif operator == 'json_count_gte':
            passed = length >= threshold
            reason = (
                f'{field_label} tem {length} itens (≥ {int(threshold)})'
                if passed
                else f'{field_label} tem {length} itens (< {int(threshold)})'
            )
        else:
            passed = length <= threshold
            reason = (
                f'{field_label} tem {length} itens (≤ {int(threshold)})'
                if passed
                else f'{field_label} tem {length} itens (> {int(threshold)})'
            )
    else:
        actual_num = _to_number(actual)
        expected_num = _to_number(expected)
        if operator == 'eq':
            if actual_num is not None and expected_num is not None:
                passed = actual_num == expected_num
            else:
                passed = str(actual or '') == str(expected or '')
            reason = (
                f'{field_label} = {_format_value(expected)}'
                if passed
                else f'{field_label} ({_format_value(actual)}) ≠ {_format_value(expected)}'
            )
        elif operator == 'neq':
            if actual_num is not None and expected_num is not None:
                passed = actual_num != expected_num
            else:
                passed = str(actual or '') != str(expected or '')
            reason = (
                f'{field_label} ≠ {_format_value(expected)}'
                if passed
                else f'{field_label} ({_format_value(actual)}) = {_format_value(expected)}'
            )
        elif operator == 'gt':
            passed = actual_num is not None and expected_num is not None and actual_num > expected_num
            reason = (
                f'{field_label} ({_format_value(actual)}) > {expected}'
                if passed
                else f'{field_label} ({_format_value(actual)}) ≤ {expected}'
            )
        elif operator == 'gte':
            passed = actual_num is not None and expected_num is not None and actual_num >= expected_num
            reason = (
                f'{field_label} ({_format_value(actual)}) ≥ {expected}'
                if passed
                else f'{field_label} ({_format_value(actual)}) < {expected}'
            )
        elif operator == 'lt':
            passed = actual_num is not None and expected_num is not None and actual_num < expected_num
            reason = (
                f'{field_label} ({_format_value(actual)}) < {expected}'
                if passed
                else f'{field_label} ({_format_value(actual)}) ≥ {expected}'
            )
        elif operator == 'lte':
            passed = actual_num is not None and expected_num is not None and actual_num <= expected_num
            reason = (
                f'{field_label} ({_format_value(actual)}) ≤ {expected}'
                if passed
                else f'{field_label} ({_format_value(actual)}) > {expected}'
            )

    return {
        'field_path': field_path,
        'field_label': field_label,
        'operator': operator,
        'passed': passed,
        'actual': actual if not isinstance(actual, (dict, list)) else f'({type(actual).__name__})',
        'expected': expected,
        'reason': reason,
    }


def evaluate_rule(lead, rule) -> dict[str, Any]:
    """Avalia uma regra completa e retorna se bateu + detalhes das condições."""
    conditions = list(rule.conditions.all())
    if not conditions:
        matched = False
        condition_results = []
    else:
        condition_results = [evaluate_condition(lead, cond) for cond in conditions]
        if rule.match_mode == 'any':
            matched = any(c['passed'] for c in condition_results)
        else:
            matched = all(c['passed'] for c in condition_results)

    return {
        'id': rule.id,
        'name': rule.name,
        'description': rule.description,
        'points': rule.points,
        'priority': rule.priority,
        'match_mode': rule.match_mode,
        'scope': getattr(rule, 'scope', 'global'),
        'matched': matched,
        'conditions': condition_results,
    }


def calculate_score(lead) -> dict[str, Any]:
    """Calcula pontuação total e breakdown para um lead."""
    from .models import ScoringRule

    rules = ScoringRule.objects.filter(is_active=True).prefetch_related('conditions')
    total = 0
    matched_rules = []
    unmatched_rules = []

    for rule in rules:
        if not rule_applies_to_lead(rule, lead):
            continue
        result = evaluate_rule(lead, rule)
        if result['matched']:
            total += rule.points
            matched_rules.append(result)
        else:
            unmatched_rules.append(result)

    return {
        'total': total,
        'matched_rules': matched_rules,
        'unmatched_rules': unmatched_rules,
    }
