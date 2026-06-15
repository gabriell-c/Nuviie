from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from leads.models import Lead
from lead_scoring.engine import calculate_score, evaluate_condition, get_field_value, get_field_registry
from lead_scoring.models import ScoringCondition, ScoringRule

User = get_user_model()


class ScoringEngineTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='scoreuser@nuviie.com',
            email='scoreuser@nuviie.com',
            password='testpass123',
        )
        ScoringRule.objects.all().delete()

    def test_exists_operator(self):
        lead = Lead.objects.create(
            user=self.user,
            name='Test',
            source='google_maps',
            normalized_phone='5511999999999',
        )
        rule = ScoringRule.objects.create(name='Tem telefone', points=20, is_active=True)
        cond = ScoringCondition.objects.create(
            rule=rule,
            field_path='normalized_phone',
            operator='exists',
        )
        result = evaluate_condition(lead, cond)
        self.assertTrue(result['passed'])

    def test_between_followers_without_site(self):
        lead = Lead.objects.create(
            user=self.user,
            name='IG Lead',
            source='instagram',
            instagram='@test',
            amenities={'follower_count': 3000},
        )
        rule = ScoringRule.objects.create(
            name='2k-5k seguidores sem site',
            points=50,
            match_mode='all',
            is_active=True,
        )
        ScoringCondition.objects.create(
            rule=rule,
            field_path='amenities.follower_count',
            operator='between',
            value={'min': 2000, 'max': 5000},
        )
        ScoringCondition.objects.create(
            rule=rule,
            field_path='website',
            operator='empty',
        )
        result = calculate_score(lead)
        self.assertEqual(result['total'], 50)
        self.assertEqual(len(result['matched_rules']), 1)

    def test_negative_points_no_cap(self):
        lead = Lead.objects.create(
            user=self.user,
            name='Com site',
            source='google_maps',
            website='https://example.com',
            website_detected_type='website',
        )
        rule = ScoringRule.objects.create(name='Penalidade site', points=-25, is_active=True)
        ScoringCondition.objects.create(
            rule=rule,
            field_path='website_detected_type',
            operator='eq',
            value='website',
        )
        result = calculate_score(lead)
        self.assertEqual(result['total'], -25)
        self.assertGreater(result['total'], -100)

    def test_unbounded_positive_score(self):
        lead = Lead.objects.create(
            user=self.user,
            name='Rich Lead',
            source='google_maps',
            normalized_phone='5511999999999',
            instagram='@x',
            category='Dentista',
        )
        r1 = ScoringRule.objects.create(name='R1', points=100, is_active=True)
        r2 = ScoringRule.objects.create(name='R2', points=100, is_active=True)
        ScoringCondition.objects.create(
            rule=r1,
            field_path='normalized_phone',
            operator='exists',
        )
        ScoringCondition.objects.create(
            rule=r2,
            field_path='instagram',
            operator='exists',
        )
        result = calculate_score(lead)
        self.assertEqual(result['total'], 200)

    def test_breakdown_includes_unmatched(self):
        lead = Lead.objects.create(
            user=self.user,
            name='Empty',
            source='google_maps',
        )
        rule = ScoringRule.objects.create(name='Precisa telefone', points=10, is_active=True)
        ScoringCondition.objects.create(
            rule=rule,
            field_path='normalized_phone',
            operator='exists',
        )
        result = calculate_score(lead)
        self.assertEqual(result['total'], 0)
        self.assertEqual(len(result['unmatched_rules']), 1)

    def test_get_field_value_derived(self):
        lead = Lead.objects.create(
            user=self.user,
            name='IG',
            source='instagram',
            total_photos=25,
        )
        self.assertEqual(get_field_value(lead, 'effective_post_count'), 25)

    def test_scope_instagram_rule_ignored_for_maps_lead(self):
        rule = ScoringRule.objects.create(
            name='IG only',
            points=30,
            scope='instagram',
            is_active=True,
        )
        ScoringCondition.objects.create(
            rule=rule,
            field_path='instagram',
            operator='exists',
        )
        maps_lead = Lead.objects.create(
            user=self.user,
            name='Maps',
            source='google_maps',
            instagram='@maps',
        )
        result = calculate_score(maps_lead)
        self.assertEqual(result['total'], 0)
        self.assertEqual(len(result['matched_rules']), 0)
        self.assertEqual(len(result['unmatched_rules']), 0)

        ig_lead = Lead.objects.create(
            user=self.user,
            name='IG',
            source='instagram',
            instagram='@ig',
        )
        result_ig = calculate_score(ig_lead)
        self.assertEqual(result_ig['total'], 30)

    def test_field_registry_includes_groups(self):
        registry = get_field_registry()
        groups = {item['group'] for item in registry}
        self.assertIn('instagram', groups)
        self.assertIn('google_maps', groups)
        self.assertIn('general', groups)


class ScoringAPITestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='apiuser@nuviie.com',
            email='apiuser@nuviie.com',
            password='testpass123',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_scoring_fields_endpoint(self):
        response = self.client.get('/api/scoring-fields/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.json()) > 10)
        paths = [f['path'] for f in response.json()]
        self.assertIn('amenities.follower_count', paths)

    def test_create_rule_with_conditions(self):
        response = self.client.post(
            '/api/scoring-rules/',
            {
                'name': 'Teste API',
                'points': 15,
                'priority': 1,
                'is_active': True,
                'match_mode': 'all',
                'conditions': [
                    {'field_path': 'instagram', 'operator': 'exists', 'value': None},
                ],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['name'], 'Teste API')
        self.assertEqual(len(data['conditions']), 1)

    def test_create_rule_with_scope(self):
        response = self.client.post(
            '/api/scoring-rules/',
            {
                'name': 'Regra IG',
                'points': 10,
                'priority': 0,
                'is_active': True,
                'match_mode': 'all',
                'scope': 'instagram',
                'conditions': [
                    {'field_path': 'is_verified', 'operator': 'is_true', 'value': None},
                ],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['scope'], 'instagram')
        self.assertEqual(response.json()['scope_display'], 'Instagram')

    def test_scoring_fields_have_group(self):
        response = self.client.get('/api/scoring-fields/')
        self.assertEqual(response.status_code, 200)
        follower = next(f for f in response.json() if f['path'] == 'amenities.follower_count')
        self.assertEqual(follower['group'], 'instagram')

    def test_recalculate_endpoint(self):
        Lead.objects.create(user=self.user, name='L1', source='google_maps')
        response = self.client.post('/api/scoring-rules/recalculate/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('recalculated', response.json())

    def test_scoring_page_requires_login(self):
        client = APIClient()
        response = client.get('/regras-pontuacao/')
        self.assertEqual(response.status_code, 302)

    def test_lead_serializer_includes_breakdown(self):
        lead = Lead.objects.create(
            user=self.user,
            name='Lead BD',
            source='google_maps',
            instagram='@foo',
        )
        response = self.client.get(f'/api/leads/{lead.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('score_breakdown', data)
        self.assertIn('total', data['score_breakdown'])
