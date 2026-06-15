from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from contracts.models import GeneratedContract
from contracts.payment_plan import build_payment_plan, plan_installments
from finance.models import FinanceEntry
from finance.services import create_second_half_on_finalizado, ensure_contract_income_on_fechado
from leads.models import Lead


User = get_user_model()


def _dummy_contract(user, **kwargs):
    defaults = {
        'user': user,
        'name': 'Doc',
        'filled_data': {},
        'pdf_file': SimpleUploadedFile('test.pdf', b'%PDF-1.4', content_type='application/pdf'),
    }
    defaults.update(kwargs)
    return GeneratedContract.objects.create(**defaults)


class PaymentPlanTests(TestCase):
    def test_build_vista_antes(self):
        plan = build_payment_plan({
            'modelo_pagamento': 'vista_antes',
            'valor_total': '3.000,00',
            'valor_vista': '2.800,00',
            'primeiro_vencimento': '2026-06-15',
        })
        self.assertEqual(plan['mode'], 'vista_antes')
        self.assertEqual(plan['total'], '2800.00')

    def test_plan_installments_parcelado(self):
        plan = build_payment_plan({
            'modelo_pagamento': 'parcelado',
            'valor_total': '1200',
            'parcelas_cartao': '3',
            'primeiro_vencimento': '2026-06-01',
        })
        inst = plan_installments(plan, date(2026, 7, 1))
        self.assertEqual(len(inst), 3)
        total = sum(Decimal(i['amount']) for i in inst)
        self.assertEqual(total, Decimal(plan['total']))

    def test_metade_antes_depois_triggers(self):
        plan = build_payment_plan({
            'modelo_pagamento': 'metade_antes_depois',
            'valor_total': '1000',
            'primeiro_vencimento': '2026-06-01',
        })
        inst = plan_installments(plan, date(2026, 7, 15))
        self.assertEqual(len(inst), 2)
        self.assertEqual(inst[0]['trigger'], 'on_link')
        self.assertEqual(inst[1]['trigger'], 'on_finalizado')

    def test_status_fechado_generates_entries(self):
        user = User.objects.create_user(username='u1', password='x')
        lead = Lead.objects.create(user=user, name='Lead A', status='fechado')
        contract = _dummy_contract(
            user,
            name='Doc',
            filled_data={'nome_cliente': 'Lead A', 'valor_total': '500'},
            payment_plan={
                'mode': 'vista_antes',
                'total': '500',
                'first_due_date': date.today().isoformat(),
            },
            client_name='Lead A',
        )
        lead.contract = contract
        lead.project_deadline = date.today()
        lead.save()
        created = ensure_contract_income_on_fechado(lead, user)
        self.assertEqual(len(created), 1)
        self.assertEqual(FinanceEntry.objects.filter(lead=lead, source='contract_auto').count(), 1)

    def test_finalizado_second_half(self):
        user = User.objects.create_user(username='u2', password='x')
        lead = Lead.objects.create(user=user, name='Lead B', status='finalizado')
        contract = _dummy_contract(
            user,
            name='Doc B',
            filled_data={'nome_cliente': 'Lead B', 'valor_total': '1000'},
            payment_plan={
                'mode': 'metade_antes_depois',
                'total': '1000',
                'first_due_date': date.today().isoformat(),
            },
            client_name='Lead B',
        )
        lead.contract = contract
        lead.project_deadline = date.today()
        lead.save()
        ensure_contract_income_on_fechado(lead, user)
        second = create_second_half_on_finalizado(lead, user)
        self.assertEqual(len(second), 1)
        self.assertTrue(
            FinanceEntry.objects.filter(lead=lead, payment_plan_key='metade_2').exists(),
        )
