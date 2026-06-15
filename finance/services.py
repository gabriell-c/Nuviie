"""Serviços financeiros: lançamentos automáticos e recorrentes."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from contracts.payment_plan import plan_installments
from finance.models import FinanceCategory, FinanceEntry

User = get_user_model()


def get_or_create_income_category() -> FinanceCategory:
    cat = FinanceCategory.objects.filter(
        name='Serviço Web', category_type='income',
    ).first()
    if cat:
        return cat
    return FinanceCategory.objects.create(
        name='Serviço Web',
        category_type='income',
        color='#10b981',
        icon='fa-globe',
    )


def get_or_create_expense_category(name: str = 'Despesas Gerais') -> FinanceCategory:
    cat = FinanceCategory.objects.filter(
        name=name, category_type='expense',
    ).first()
    if cat:
        return cat
    return FinanceCategory.objects.create(
        name=name,
        category_type='expense',
        color='#ef4444',
        icon='fa-arrow-down',
    )


def _entry_exists(contract_id: int, plan_key: str) -> bool:
    return FinanceEntry.objects.filter(
        contract_id=contract_id,
        payment_plan_key=plan_key,
    ).exclude(status='cancelled').exists()


@transaction.atomic
def generate_entries_from_plan(
    lead,
    contract,
    *,
    triggers: tuple[str, ...] = ('on_link',),
    created_by=None,
) -> list[FinanceEntry]:
    """Gera lançamentos pendentes idempotentes conforme plano do contrato."""
    plan = contract.payment_plan or {}
    if not plan:
        return []

    installments = plan_installments(plan, lead.project_deadline)
    category = get_or_create_income_category()
    client = contract.client_name or lead.name
    created: list[FinanceEntry] = []

    for inst in installments:
        if inst['trigger'] not in triggers:
            continue
        key = inst['key']
        if _entry_exists(contract.id, key):
            continue
        due = date.fromisoformat(inst['due_date'])
        entry = FinanceEntry.objects.create(
            entry_type='income',
            title=f'Contrato — {client} ({key.replace("_", " ")})',
            amount=Decimal(inst['amount']),
            date=due,
            due_date=due,
            category=category,
            lead=lead,
            contract=contract,
            status='pending',
            source='contract_auto',
            payment_plan_key=key,
            created_by=created_by,
            notes=f'Gerado automaticamente do contrato #{contract.id}',
        )
        created.append(entry)
    return created


def ensure_contract_income_on_fechado(lead, user=None) -> list[FinanceEntry]:
    if not lead.contract_id:
        return []
    contract = lead.contract
    return generate_entries_from_plan(
        lead, contract, triggers=('on_link',), created_by=user,
    )


def create_second_half_on_finalizado(lead, user=None) -> list[FinanceEntry]:
    if not lead.contract_id:
        return []
    contract = lead.contract
    plan = contract.payment_plan or {}
    if plan.get('mode') != 'metade_antes_depois':
        return []
    return generate_entries_from_plan(
        lead, contract, triggers=('on_finalizado',), created_by=user,
    )


def generate_recurring_occurrence(parent: FinanceEntry, target_date: date | None = None) -> FinanceEntry | None:
    if not parent.is_recurring or not parent.recurrence_rule:
        return None
    rule = parent.recurrence_rule
    if rule.get('frequency') != 'monthly':
        return None
    day = int(rule.get('day_of_month') or parent.date.day)
    today = target_date or timezone.localdate()
    try:
        due = today.replace(day=min(day, 28))
    except ValueError:
        due = today.replace(day=28)
    key = f'recurring_{parent.id}_{due.isoformat()}'
    if FinanceEntry.objects.filter(payment_plan_key=key).exists():
        return None
    return FinanceEntry.objects.create(
        entry_type=parent.entry_type,
        title=parent.title,
        amount=parent.amount,
        date=due,
        due_date=due,
        category=parent.category,
        lead=parent.lead,
        status='pending',
        source='recurring',
        payment_plan_key=key,
        parent_recurring=parent,
        is_recurring=False,
        attachment_kind='none',
        created_by=parent.created_by,
        notes=parent.notes,
    )


def process_due_recurring_entries() -> int:
    """Gera ocorrências mensais para entradas recorrentes ativas."""
    count = 0
    today = timezone.localdate()
    for parent in FinanceEntry.objects.filter(is_recurring=True, status='confirmed'):
        if generate_recurring_occurrence(parent, today):
            count += 1
    return count
