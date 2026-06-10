from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from audit.models import ActivityLog


class AuditTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='audituser',
            email='audituser@nuviie.com',
            password='testpassword123',
        )
        self.client = Client()

    def test_login_creates_activity_log(self):
        self.client.login(username='audituser@nuviie.com', password='testpassword123')
        self.assertTrue(
            ActivityLog.objects.filter(user=self.user, action='login').exists()
        )

    def test_history_page_requires_auth(self):
        response = self.client.get(reverse('audit_history'))
        self.assertEqual(response.status_code, 302)

    def test_history_page_authenticated(self):
        self.client.login(username='audituser@nuviie.com', password='testpassword123')
        response = self.client.get(reverse('audit_history'))
        self.assertEqual(response.status_code, 200)
