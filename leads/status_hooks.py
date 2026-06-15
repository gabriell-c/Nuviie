"""Gatilhos ao mudar status do lead."""

from finance.services import (
    create_second_half_on_finalizado,
    ensure_contract_income_on_fechado,
)
from notifications.services import check_deadline_notifications


def on_lead_status_changed(lead, old_status, new_status, user=None):
    if new_status == 'fechado' and old_status != 'fechado':
        ensure_contract_income_on_fechado(lead, user)
    if new_status == 'finalizado' and old_status != 'finalizado':
        create_second_half_on_finalizado(lead, user)
    check_deadline_notifications()
