from unittest.mock import patch, MagicMock

from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from authentication.whatsapp import clean_phone_number
from leads.models import Lead


class NuviieSaaSTestCase(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(
            username="testuser",
            email="testuser@nuviie.com",
            password="testpassword123",
            first_name="Test",
            last_name="User",
            phone_number="5511999999999",
        )
        self.client = Client()

    def test_user_creation(self):
        self.assertEqual(self.user.email, "testuser@nuviie.com")
        self.assertEqual(self.user.phone_number, "5511999999999")
        self.assertTrue(self.user.check_password("testpassword123"))

    def test_phone_normalization(self):
        self.assertEqual(clean_phone_number("+55 (11) 98888-8888"), "5511988888888")
        self.assertEqual(clean_phone_number("  55 11 97777 7777  "), "5511977777777")

    def test_lead_quality_score(self):
        lead = Lead.objects.create(
            user=self.user,
            name="Clínica Odonto Test",
            category="Dentista",
            city="São Paulo",
            phone_number="(11) 99999-9999",
            normalized_phone="5511999999999",
            website="https://odontotest.com",
            website_detected_type="website",
            instagram="@odontotest",
            maps_url="https://maps.google.com/?cid=123",
            address="Rua Teste, 100",
            profile_picture_url="https://example.com/photo.jpg",
            source="google_maps",
            status="novo",
        )
        self.assertGreaterEqual(lead.quality_score, 80)

        poor_lead = Lead.objects.create(
            user=self.user,
            name="Anon Business",
            source="google_maps",
            status="novo",
        )
        self.assertEqual(poor_lead.quality_score, 0)

    @patch('leads.instagram_scraper.fetch_instagram_profile_pic', return_value=None)
    @patch('leads.instagram_scraper.requests.post')
    def test_instagram_scraper_filters(self, mock_post, _mock_pic):
        from leads.instagram_scraper import run_instagram_scraper

        html = """
        <div class="result">
          <div class="result__title"><a href="https://instagram.com/advogado_verificado/">Adv</a></div>
          <div class="result__snippet">Escritório verificado em Curitiba https://escritorio.com.br</div>
        </div>
        <div class="result">
          <div class="result__title"><a href="https://instagram.com/outro_adv/">Outro</a></div>
          <div class="result__snippet">Perfil em Curitiba</div>
        </div>
        """
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_post.return_value = mock_resp

        saved, skipped = run_instagram_scraper(
            user=self.user,
            niche="Advogados",
            location="Curitiba",
            limit=1,
            only_verified=True,
            only_with_bio_link=True,
        )
        self.assertEqual(saved, 1)
        lead = Lead.objects.get(user=self.user, source='instagram')
        self.assertTrue(lead.is_verified)
        self.assertIsNotNone(lead.website)
        self.assertTrue(lead.website.startswith("http"))

    def test_lead_api_search_filter(self):
        Lead.objects.create(
            user=self.user,
            name="Padaria Central",
            category="Padaria",
            city="Campinas",
            source="google_maps",
            status="novo",
        )
        self.client.login(username="testuser@nuviie.com", password="testpassword123")
        response = self.client.get('/api/leads/?search=Padaria')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], "Padaria Central")

    def test_bulk_delete_leads(self):
        ids = []
        for i in range(3):
            lead = Lead.objects.create(
                user=self.user,
                name=f"Lead {i}",
                source="google_maps",
                status="novo",
            )
            ids.append(lead.id)

        self.client.login(username="testuser@nuviie.com", password="testpassword123")
        response = self.client.post(
            '/api/leads/bulk-delete/',
            data={'ids': ids[:2]},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['deleted'], 2)
        self.assertEqual(Lead.objects.filter(user=self.user).count(), 1)

    def test_delete_all_leads(self):
        for i in range(5):
            Lead.objects.create(
                user=self.user,
                name=f"Lead {i}",
                source="google_maps",
                status="novo",
            )

        self.client.login(username="testuser@nuviie.com", password="testpassword123")
        response = self.client.post(
            '/api/leads/delete-all/',
            data={'confirm': True},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['deleted'], 5)
        self.assertEqual(Lead.objects.filter(user=self.user).count(), 0)

    def test_health_endpoint(self):
        response = self.client.get('/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})


class ImportUtilsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='importuser@nuviie.com',
            email='importuser@nuviie.com',
            password='testpassword123',
        )

    def test_save_leads_from_dicts_dedup(self):
        from leads.import_utils import save_leads_from_dicts

        payload = [{
            'name': 'Escritório Teste',
            'category': 'Advogado',
            'city': 'Ribeirão Preto',
            'phone_number': '(16) 99999-8888',
            'normalized_phone': '5516999998888',
            'source': 'google_maps',
        }]
        saved, skipped = save_leads_from_dicts(self.user, payload)
        self.assertEqual(saved, 1)
        saved2, skipped2 = save_leads_from_dicts(self.user, payload)
        self.assertEqual(saved2, 0)
        self.assertEqual(skipped2, 1)

    @override_settings(
        NUVIIE_EXTENSION_TOKEN='test-token-123',
        NUVIIE_EXTENSION_USER='importuser@nuviie.com',
    )
    def test_bulk_import_endpoint(self):
        response = self.client.post(
            '/api/leads/bulk-import/',
            data={
                'city': 'Ribeirão Preto',
                'leads': [{
                    'name': 'Clínica Bulk',
                    'category': 'Dentista',
                    'source': 'google_maps',
                }],
            },
            content_type='application/json',
            HTTP_X_NUVIIE_TOKEN='test-token-123',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['saved'], 1)
        self.assertTrue(Lead.objects.filter(user=self.user, name='Clínica Bulk').exists())

    @override_settings(NUVIIE_EXTENSION_TOKEN='test-token-123')
    def test_bulk_import_invalid_token(self):
        response = self.client.post(
            '/api/leads/bulk-import/',
            data={'leads': []},
            content_type='application/json',
            HTTP_X_NUVIIE_TOKEN='wrong',
        )
        self.assertEqual(response.status_code, 401)


class WebsiteUtilsTests(TestCase):
    def test_detect_website_type(self):
        from leads.website_utils import detect_website_type

        self.assertEqual(detect_website_type('https://instagram.com/user'), 'instagram')
        self.assertEqual(detect_website_type('https://example.com'), 'website')
        self.assertEqual(detect_website_type(''), 'website')
