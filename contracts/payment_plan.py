"""Plano de pagamento estruturado a partir do formulário de contrato."""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any


PAYMENT_MODES = (
    'vista_antes',
    'vista_depois',
    'parcelado',
    'metade_antes_depois',
)


def _parse_money(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        s = str(value).strip().replace('.', '').replace(',', '.')
        s = re.sub(r'[^\d.]', '', s)
        if not s:
            return None
        return Decimal(s).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _parse_date_br(value: Any) -> date | None:
    if not value:
        return None
    s = str(value).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def build_payment_plan(filled_data: dict) -> dict:
    """Monta plano JSON a partir dos campos do POST / filled_data."""
    data = filled_data or {}
    mode = (data.get('modelo_pagamento') or 'vista_antes').strip()

    valor_total = _parse_money(data.get('valor_total'))
    valor_vista = _parse_money(data.get('valor_vista'))
    parcelas = max(1, _parse_int(data.get('parcelas_cartao'), 12))
    acrescimo = _parse_int(data.get('acrescimo_cartao_percentual'), 0)
    vista_quando = (data.get('vista_quando') or 'antes').strip()

    if mode == 'vista_antes':
        amount = valor_vista or valor_total
        mode_key = 'vista_antes'
    elif mode == 'vista_depois':
        amount = valor_vista or valor_total
        mode_key = 'vista_depois'
    elif mode == 'metade_antes_depois':
        amount = valor_total
        mode_key = 'metade_antes_depois'
    else:
        base = valor_total or Decimal('0')
        if acrescimo:
            amount = (base * (1 + Decimal(acrescimo) / 100)).quantize(Decimal('0.01'))
        else:
            amount = base
        mode_key = 'parcelado'

    first_due = _parse_date_br(data.get('primeiro_vencimento')) or date.today()

    plan = {
        'mode': mode_key,
        'total': str(amount or Decimal('0')),
        'valor_total_original': str(valor_total or Decimal('0')),
        'valor_vista': str(valor_vista) if valor_vista else None,
        'vista_quando': vista_quando,
        'parcelas': parcelas,
        'acrescimo_percent': acrescimo,
        'first_due_date': first_due.isoformat(),
        'prazo_desenvolvimento_dias': _parse_int(data.get('prazo_desenvolvimento_dias'), 30),
        'data_assinatura': (data.get('data_assinatura') or '').strip(),
    }
    return plan


def compute_project_deadline(filled_data: dict, payment_plan: dict | None = None) -> date | None:
    plan = payment_plan or build_payment_plan(filled_data)
    days = plan.get('prazo_desenvolvimento_dias', 30)
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 30
    start = _parse_date_br(filled_data.get('data_assinatura_iso')) or date.today()
    # dias úteis aproximados: 5/7
    calendar_days = int(days * 7 / 5) + 1
    return start + timedelta(days=calendar_days)


def plan_installments(payment_plan: dict, project_deadline: date | None) -> list[dict]:
    """Lista de parcelas: amount, due_date, key, trigger."""
    mode = payment_plan.get('mode', 'vista_antes')
    total = Decimal(payment_plan.get('total') or '0')
    first_due = _parse_date_br(payment_plan.get('first_due_date')) or date.today()
    out: list[dict] = []

    if mode == 'vista_antes':
        out.append({
            'key': 'vista_1',
            'amount': str(total),
            'due_date': first_due.isoformat(),
            'trigger': 'on_link',
        })
    elif mode == 'vista_depois':
        due = project_deadline or first_due
        out.append({
            'key': 'vista_1',
            'amount': str(total),
            'due_date': due.isoformat(),
            'trigger': 'on_link',
        })
    elif mode == 'metade_antes_depois':
        half = (total / 2).quantize(Decimal('0.01'))
        rest = total - half
        out.append({
            'key': 'metade_1',
            'amount': str(half),
            'due_date': first_due.isoformat(),
            'trigger': 'on_link',
        })
        out.append({
            'key': 'metade_2',
            'amount': str(rest),
            'due_date': (project_deadline or first_due).isoformat(),
            'trigger': 'on_finalizado',
        })
    elif mode == 'parcelado':
        n = max(1, int(payment_plan.get('parcelas') or 1))
        base = (total / n).quantize(Decimal('0.01'))
        for i in range(n):
            amt = base if i < n - 1 else total - base * (n - 1)
            due = first_due + timedelta(days=30 * i)
            out.append({
                'key': f'parcela_{i + 1}',
                'amount': str(amt),
                'due_date': due.isoformat(),
                'trigger': 'on_link',
            })
    return out
