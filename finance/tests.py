from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from contracts.models import GeneratedContract
from finance.models import FinanceCategory, FinanceEntry
from finance.services import generate_entries_from_plan
from leads.models import Lead


User = get_user_model()


def _dummy_contract(user, **kwargs):
    defaults = {
        'user': user,
        'name': 'Contrato teste',
        'filled_data': {},
        'pdf_file': SimpleUploadedFile('test.pdf', b'%PDF-1.4', content_type='application/pdf'),
    }
    defaults.update(kwargs)
    return GeneratedContract.objects.create(**defaults)


class FinanceEntryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='financeuser',
            email='finance@nuviie.com',
            password='testpass123',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.income_cat = FinanceCategory.objects.filter(
            name='Serviço Web', category_type='income',
        ).first() or FinanceCategory.objects.create(
            name='Test Income', category_type='income', color='#10b981',
        )
        self.expense_cat = FinanceCategory.objects.filter(
            category_type='expense',
        ).first() or FinanceCategory.objects.create(
            name='Test Expense', category_type='expense', color='#ef4444',
        )

    def test_create_income_entry_via_api(self):
        payload = {
            'entry_type': 'income',
            'title': 'Pagamento cliente',
            'amount': '1500.00',
            'date': date.today().isoformat(),
            'category': self.income_cat.id,
            'status': 'confirmed',
            'attachment_kind': 'receipt',
        }
        r = self.client.post('/api/finance/entries/', payload, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(FinanceEntry.objects.count(), 1)

    def test_attachment_kind_validation_expense_statement(self):
        payload = {
            'entry_type': 'expense',
            'title': 'Hospedagem',
            'amount': '99.00',
            'date': date.today().isoformat(),
            'category': self.expense_cat.id,
            'status': 'confirmed',
            'attachment_kind': 'statement',
        }
        r = self.client.post('/api/finance/entries/', payload, content_type='application/json')
        self.assertEqual(r.status_code, 201)

    def test_attachment_kind_rejects_statement_on_income(self):
        payload = {
            'entry_type': 'income',
            'title': 'Entrada inválida',
            'amount': '100.00',
            'date': date.today().isoformat(),
            'category': self.income_cat.id,
            'status': 'pending',
            'attachment_kind': 'statement',
        }
        r = self.client.post('/api/finance/entries/', payload, content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_export_xlsx(self):
        from django.urls import reverse
        FinanceEntry.objects.create(
            entry_type='income', title='Test', amount=Decimal('500'),
            date=date.today(), category=self.income_cat, status='confirmed',
        )
        url = reverse('finance-entry-export-entries')
        r = self.client.get(url, {'export_format': 'xlsx'})
        self.assertEqual(r.status_code, 200, msg=getattr(r, 'content', b'')[:200])
        self.assertIn('spreadsheetml', r['Content-Type'])

    def test_contract_auto_entries_idempotent(self):
        lead = Lead.objects.create(user=self.user, name='Cliente X', status='novo')
        contract = _dummy_contract(
            self.user,
            name='Contrato X',
            filled_data={'nome_cliente': 'Cliente X', 'valor_total': '2000'},
            payment_plan={
                'mode': 'vista_antes',
                'total': '2000',
                'first_due_date': date.today().isoformat(),
                'parcelas': 1,
            },
            client_name='Cliente X',
        )
        lead.contract = contract
        lead.project_deadline = date.today() + timedelta(days=30)
        lead.save()
        first = generate_entries_from_plan(lead, contract, triggers=('on_link',), created_by=self.user)
        second = generate_entries_from_plan(lead, contract, triggers=('on_link',), created_by=self.user)
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)
        self.assertEqual(FinanceEntry.objects.filter(contract=contract).count(), 1)
