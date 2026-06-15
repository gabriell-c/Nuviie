"""Associação contrato ↔ lead e sincronização de prazos/valores."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from contracts.payment_plan import build_payment_plan, compute_project_deadline
from finance.services import generate_entries_from_plan


@transaction.atomic
def link_contract_to_lead(contract, lead, user=None, *, generate_finance: bool = True):
    filled = contract.filled_data or {}
    if not contract.payment_plan:
        contract.payment_plan = build_payment_plan(filled)
    deadline = compute_project_deadline(filled, contract.payment_plan)
    total = contract.payment_plan.get('total') or filled.get('valor_total') or '0'
    try:
        contract_value = Decimal(str(total).replace(',', '.'))
    except Exception:
        contract_value = None

    contract.lead = lead
    contract.client_name = contract.client_name or filled.get('nome_cliente') or lead.name
    contract.save(update_fields=['lead', 'client_name', 'payment_plan'])

    lead.contract = contract
    lead.project_deadline = deadline
    lead.contract_value = contract_value
    lead.save(update_fields=['contract', 'project_deadline', 'contract_value'])

    created = []
    if generate_finance:
        triggers = ('on_link',)
        if lead.status == 'fechado':
            triggers = ('on_link',)
        created = generate_entries_from_plan(
            lead, contract, triggers=triggers, created_by=user,
        )
    return lead, created


@transaction.atomic
def unlink_contract_from_lead(contract, lead):
    if lead.contract_id == contract.id:
        lead.contract = None
        lead.save(update_fields=['contract'])
    if contract.lead_id == lead.id:
        contract.lead = None
        contract.save(update_fields=['lead'])
