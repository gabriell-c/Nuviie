from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


class MonitoringTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='monitoruser',
            email='monitoruser@nuviie.com',
            password='testpassword123',
        )
        self.client = Client()

    def test_analytics_api_requires_auth(self):
        response = self.client.get(reverse('monitoring_api'))
        self.assertEqual(response.status_code, 302)

    def test_analytics_api_authenticated(self):
        self.client.login(username='monitoruser@nuviie.com', password='testpassword123')
        response = self.client.get(reverse('monitoring_api'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('cpu', data)
        self.assertIn('memory', data)
        self.assertIn('system', data)

    def test_analytics_page(self):
        self.client.login(username='monitoruser@nuviie.com', password='testpassword123')
        response = self.client.get(reverse('monitoring_analytics'))
        self.assertEqual(response.status_code, 200)
