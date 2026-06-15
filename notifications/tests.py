from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from contracts.models import GeneratedContract
from leads.models import Lead
from notifications.models import Notification
from notifications.services import check_deadline_notifications


User = get_user_model()


class DeadlineNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='notifyuser',
            email='notify@nuviie.com',
            password='testpass123',
        )

    def _lead_with_deadline(self, days_ahead):
        contract = GeneratedContract.objects.create(
            user=self.user,
            name='C',
            filled_data={},
            client_name='Cliente',
            pdf_file=SimpleUploadedFile('c.pdf', b'%PDF', content_type='application/pdf'),
        )
        return Lead.objects.create(
            user=self.user,
            name='Projeto Teste',
            status='fechado',
            contract=contract,
            project_deadline=timezone.localdate() + timedelta(days=days_ahead),
        )

    def test_warning_at_4_days(self):
        self._lead_with_deadline(4)
        count = check_deadline_notifications()
        self.assertGreaterEqual(count, 1)
        self.assertTrue(
            Notification.objects.filter(level='warning', user=self.user).exists(),
        )

    def test_danger_at_2_days(self):
        self._lead_with_deadline(2)
        check_deadline_notifications()
        self.assertTrue(
            Notification.objects.filter(level='danger', user=self.user).exists(),
        )

    def test_dedupe_same_deadline(self):
        self._lead_with_deadline(2)
        check_deadline_notifications()
        first_count = Notification.objects.filter(user=self.user).count()
        check_deadline_notifications()
        self.assertEqual(Notification.objects.filter(user=self.user).count(), first_count)

    def test_lead_deadline_urgency(self):
        lead = self._lead_with_deadline(2)
        self.assertEqual(lead.deadline_urgency(), 'danger')
        lead.project_deadline = timezone.localdate() + timedelta(days=3)
        self.assertEqual(lead.deadline_urgency(), 'warning')
        lead.project_deadline = timezone.localdate() + timedelta(days=10)
        self.assertEqual(lead.deadline_urgency(), 'none')
