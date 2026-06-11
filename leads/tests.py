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

    def test_save_leads_from_dicts_dedup_instagram_handle(self):
        from leads.import_utils import save_leads_from_dicts

        Lead.objects.create(
            user=self.user,
            name='Dr João Original',
            instagram='@clinica.teste',
            source='instagram',
            status='novo',
        )
        payload = [{
            'name': 'Clínica Teste Odonto',
            'instagram': '@clinica.teste',
            'city': 'Ribeirão Preto',
            'source': 'instagram',
            'amenities': {'recent_posts': [{'type': 'photo'}]},
        }]
        saved, skipped = save_leads_from_dicts(self.user, payload)
        self.assertEqual(saved, 1)
        self.assertEqual(skipped, 0)
        existing = Lead.objects.get(user=self.user, instagram__iexact='@clinica.teste')
        self.assertEqual(existing.amenities.get('recent_posts'), [{'type': 'photo'}])
        self.assertEqual(Lead.objects.filter(user=self.user, instagram__iexact='@clinica.teste').count(), 1)

    def test_save_leads_updates_ig_when_same_name_exists(self):
        from leads.import_utils import save_leads_from_dicts

        Lead.objects.create(
            user=self.user,
            name='FCS Advocacia',
            instagram='@fcsadvocacia',
            source='instagram',
            status='novo',
            amenities={'follower_count': 100},
        )
        payload = [{
            'name': 'FCS Advocacia',
            'instagram': '@fcsadvocacia',
            'source': 'instagram',
            'amenities': {
                'follower_count': 1340,
                'recent_posts': [{'shortcode': 'abc123', 'type': 'photo', 'caption': 'Teste'}],
            },
        }]
        saved, skipped = save_leads_from_dicts(self.user, payload)
        self.assertEqual(saved, 1)
        self.assertEqual(skipped, 0)
        lead = Lead.objects.get(user=self.user, instagram__iexact='@fcsadvocacia')
        self.assertEqual(len(lead.amenities.get('recent_posts', [])), 1)
        self.assertEqual(lead.amenities.get('follower_count'), 1340)

    def test_save_leads_updates_phone_from_whatsapp_normalized(self):
        from leads.import_utils import save_leads_from_dicts

        Lead.objects.create(
            user=self.user,
            name='Advogado WA',
            instagram='@advwa',
            source='instagram',
            status='novo',
            website_detected_type='whatsapp',
            normalized_phone='5516999998888',
        )
        payload = [{
            'name': 'Advogado WA',
            'instagram': '@advwa',
            'source': 'instagram',
            'website_detected_type': 'whatsapp',
            'normalized_phone': '5516999998888',
            'phone_number': '(16) 99999-8888',
        }]
        saved, skipped = save_leads_from_dicts(self.user, payload)
        self.assertEqual(saved, 1)
        lead = Lead.objects.get(user=self.user, instagram__iexact='@advwa')
        self.assertEqual(lead.phone_number, '(16) 99999-8888')
        self.assertEqual(lead.normalized_phone, '5516999998888')

    def test_instagram_export_limits_and_strips_media_urls(self):
        from leads.lead_export import build_lead_profile, lead_to_json
        import json

        comments = [{'author': '@u1', 'text': f'c{i}'} for i in range(5)]
        posts = [{
            'type': 'photo',
            'shortcode': f'p{i}',
            'taken_at': 1000 + i,
            'caption': f'Post {i}',
            'image_url': f'https://cdn.example.com/{i}.jpg',
            'video_url': f'https://cdn.example.com/{i}.mp4',
            'comments': comments,
        } for i in range(8)]
        lead = Lead.objects.create(
            user=self.user,
            name='Export IG Test',
            instagram='@exporttest',
            source='instagram',
            status='novo',
            amenities={'recent_posts': posts, 'recent_reels': [], 'follower_count': 100},
        )
        profile = build_lead_profile(lead)
        ig = profile.get('instagram', {})
        ultimas = ig.get('ultimas_publicacoes', [])
        self.assertLessEqual(len(ultimas), 5)
        raw = lead_to_json(profile)
        ig_block = json.loads(raw)['instagram']
        for item in ig_block['ultimas_publicacoes']:
            self.assertNotIn('image_url', item)
            self.assertNotIn('video_url', item)
            self.assertLessEqual(len(item.get('comments', [])), 3)

    def test_instagram_quality_with_posts_and_recency(self):
        from datetime import datetime, timezone
        recent_ts = int(datetime.now(timezone.utc).timestamp()) - (86400 * 10)
        lead = Lead.objects.create(
            user=self.user,
            name='Clínica Ativa IG',
            instagram='@clinicaativa',
            source='instagram',
            status='novo',
            total_photos=45,
            profile_picture_url='https://example.com/pic.jpg',
            website_detected_type='linktree',
            amenities={'latest_post_at': recent_ts, 'post_count': 45},
        )
        self.assertGreaterEqual(lead.quality_score, 40)

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


class LeadExportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='exportuser@nuviie.com',
            email='exportuser@nuviie.com',
            password='testpassword123',
        )
        self.lead = Lead.objects.create(
            user=self.user,
            name='Dr Murilo Campos',
            category='Dentista',
            city='Ribeirão Preto',
            phone_number='(16) 99999-8888',
            normalized_phone='5516999998888',
            website='https://drmurilocampos.com.br',
            instagram='@dr.murilocampos',
            facebook='https://www.facebook.com/p/Dr-Murilo-Campo',
            address='Avenida Maurilio Biagi 800',
            rating=5.0,
            review_count=2,
            recent_reviews=[{
                'author': 'Amarilda',
                'rating': 5,
                'text': 'muito bom',
            }],
            business_hours={'seg': '08:00–18:00', 'aberto_agora': True},
            source='google_maps',
            status='novo',
        )

    def test_lead_to_markdown_contains_sections(self):
        from leads.lead_export import build_lead_profile, lead_to_markdown

        profile = build_lead_profile(self.lead)
        md = lead_to_markdown(profile)
        self.assertIn('# Dr Murilo Campos', md)
        self.assertIn('Instagram', md)
        self.assertIn('@dr.murilocampos', md)
        self.assertIn('Amarilda', md)
        self.assertIn('5 estrelas', md)

    def test_export_endpoint_md_and_json(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.user)

        detail = client.get(f'/api/leads/{self.lead.id}/')
        self.assertEqual(detail.status_code, 200)

        md_resp = client.get(f'/api/leads/{self.lead.id}/export/?file_type=md')
        self.assertEqual(md_resp.status_code, 200)
        self.assertIn('text/markdown', md_resp['Content-Type'])
        self.assertIn('attachment', md_resp['Content-Disposition'])
        self.assertIn(b'Dr Murilo Campos', md_resp.content)

        json_resp = client.get(f'/api/leads/{self.lead.id}/export/?file_type=json')
        self.assertEqual(json_resp.status_code, 200)
        import json
        data = json.loads(json_resp.content)
        self.assertEqual(data['identificacao']['nome'], 'Dr Murilo Campos')
        self.assertEqual(len(data['avaliacoes']['recentes']), 1)


class ProfilePictureTests(TestCase):
    _PNG_DATA_URL = (
        'data:image/png;base64,'
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
    )

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='picuser@nuviie.com',
            email='picuser@nuviie.com',
            password='testpassword123',
        )
        self.client = Client()
        self.client.login(username='picuser@nuviie.com', password='testpassword123')

    def test_save_leads_profile_picture_from_base64(self):
        from django.core.files.storage import default_storage
        from leads.import_utils import save_leads_from_dicts

        payload = [{
            'name': 'Perfil Com Foto',
            'instagram': '@fototest',
            'source': 'instagram',
            'profile_picture_data': self._PNG_DATA_URL,
            'profile_picture_url': 'https://instagram.frao6-1.fna.fbcdn.net/v/test.jpg',
        }]
        saved, skipped = save_leads_from_dicts(self.user, payload)
        self.assertEqual(saved, 1)
        lead = Lead.objects.get(user=self.user, instagram__iexact='@fototest')
        self.assertIn('lead_avatars', lead.profile_picture_url or '')
        self.assertTrue(default_storage.exists('lead_avatars/fototest.png'))

    def test_update_instagram_lead_overwrites_profile_picture(self):
        from leads.import_utils import save_leads_from_dicts

        Lead.objects.create(
            user=self.user,
            name='Perfil Com Foto',
            instagram='@fototest',
            source='instagram',
            status='novo',
            profile_picture_url='https://instagram.frao6-1.fna.fbcdn.net/old.jpg',
        )
        payload = [{
            'name': 'Perfil Com Foto',
            'instagram': '@fototest',
            'source': 'instagram',
            'profile_picture_data': self._PNG_DATA_URL,
        }]
        saved, skipped = save_leads_from_dicts(self.user, payload)
        self.assertEqual(saved, 1)
        lead = Lead.objects.get(user=self.user, instagram__iexact='@fototest')
        self.assertIn('lead_avatars', lead.profile_picture_url or '')

    def test_avatar_endpoint_serves_local_file(self):
        from leads.import_utils import save_leads_from_dicts

        payload = [{
            'name': 'Avatar Endpoint',
            'instagram': '@avataruser',
            'source': 'instagram',
            'profile_picture_data': self._PNG_DATA_URL,
        }]
        save_leads_from_dicts(self.user, payload)
        lead = Lead.objects.get(user=self.user, instagram__iexact='@avataruser')

        resp = self.client.get(f'/api/leads/{lead.id}/avatar/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('image/', resp['Content-Type'])
        self.assertGreater(len(resp.content), 50)

    def test_serializer_profile_picture_display_url_local(self):
        from rest_framework.test import APIClient
        from leads.import_utils import save_leads_from_dicts

        save_leads_from_dicts(self.user, [{
            'name': 'Display URL Local',
            'instagram': '@displaylocal',
            'source': 'instagram',
            'profile_picture_data': self._PNG_DATA_URL,
        }])
        lead = Lead.objects.get(user=self.user, instagram__iexact='@displaylocal')

        api = APIClient()
        api.force_authenticate(user=self.user)
        resp = api.get(f'/api/leads/{lead.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('lead_avatars', resp.data['profile_picture_display_url'])

    def test_serializer_profile_picture_display_url_cdn_proxy(self):
        from rest_framework.test import APIClient

        lead = Lead.objects.create(
            user=self.user,
            name='Display URL CDN',
            instagram='@displaycdn',
            source='instagram',
            status='novo',
            profile_picture_url='https://instagram.frao6-1.fna.fbcdn.net/v/test.jpg',
        )
        api = APIClient()
        api.force_authenticate(user=self.user)
        resp = api.get(f'/api/leads/{lead.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('/avatar/', resp.data['profile_picture_display_url'])


class WebsiteUtilsTests(TestCase):
    def test_detect_website_type(self):
        from leads.website_utils import detect_website_type

        self.assertEqual(detect_website_type('https://instagram.com/user'), 'instagram')
        self.assertEqual(detect_website_type('https://example.com'), 'website')
        self.assertEqual(detect_website_type(''), 'website')
