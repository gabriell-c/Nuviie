"""Testes da auditoria de sites."""

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from leads.models import Lead
from site_audit.export import audit_to_json, audit_to_markdown
from site_audit.models import SiteAuditReport, SiteAuditVisualAsset
from site_audit.pagespeed import build_summary, parse_lighthouse_result, _extract_table_elements

User = get_user_model()

FIXTURE_PATH = Path(__file__).resolve().parent / 'fixtures' / 'pagespeed_sample.json'

SAMPLE_PSI = {
    'lighthouseResult': {
        'categories': {
            'performance': {'score': 0.72, 'auditRefs': [{'id': 'largest-contentful-paint'}]},
            'seo': {'score': 0.91, 'auditRefs': [{'id': 'meta-description'}]},
            'accessibility': {'score': 0.88, 'auditRefs': []},
            'best-practices': {'score': 0.95, 'auditRefs': []},
        },
        'audits': {
            'largest-contentful-paint': {
                'id': 'largest-contentful-paint',
                'title': 'Largest Contentful Paint',
                'description': 'LCP desc',
                'score': 0.45,
                'numericValue': 4200,
                'displayValue': '4.2 s',
                'scoreDisplayMode': 'numeric',
            },
            'meta-description': {
                'id': 'meta-description',
                'title': 'Document does not have a meta description',
                'description': 'Meta description is missing',
                'score': 0,
                'scoreDisplayMode': 'binary',
            },
            'render-blocking-resources': {
                'id': 'render-blocking-resources',
                'title': 'Eliminate render-blocking resources',
                'description': 'Resources blocking',
                'score': 0.3,
                'scoreDisplayMode': 'numeric',
                'details': {'type': 'opportunity', 'overallSavingsMs': 850},
            },
        },
    }
}


class PageSpeedParserTests(TestCase):
    def test_parse_scores_and_issues(self):
        result = parse_lighthouse_result(SAMPLE_PSI)
        self.assertEqual(result['scores']['performance'], 72)
        self.assertEqual(result['scores']['seo'], 91)
        self.assertIn('lcp_ms', result['core_web_vitals'])
        perf_titles = [i['title'] for i in result['recommendations']['performance']]
        self.assertTrue(any('render-blocking' in t.lower() or 'Largest' in t for t in perf_titles))
        seo_titles = [i['title'] for i in result['recommendations']['seo']]
        self.assertTrue(any('meta description' in t.lower() for t in seo_titles))

    def test_fixture_extracts_table_elements(self):
        data = json.loads(FIXTURE_PATH.read_text(encoding='utf-8'))
        audit = data['lighthouseResult']['audits']['color-contrast']
        elements = _extract_table_elements(audit)
        self.assertEqual(len(elements), 1)
        self.assertIn('snippet', elements[0])
        self.assertIn('subtitle', elements[0]['snippet'])

    def test_parse_includes_elements_on_issues(self):
        data = json.loads(FIXTURE_PATH.read_text(encoding='utf-8'))
        result = parse_lighthouse_result(data)
        a11y = result['recommendations']['accessibility']
        contrast = next(i for i in a11y if i['id'] == 'color-contrast')
        self.assertTrue(contrast.get('elements'))
        self.assertEqual(contrast['elements'][0]['selector'], 'body > div.hero > p.subtitle')

    def test_build_summary(self):
        parsed = parse_lighthouse_result(SAMPLE_PSI)
        summary = build_summary(
            'https://example.com',
            {'mobile': parsed['scores'], 'desktop': parsed['scores']},
            {'mobile': parsed['core_web_vitals'], 'desktop': parsed['core_web_vitals']},
            {'mobile': parsed['recommendations'], 'desktop': parsed['recommendations']},
        )
        self.assertIn('example.com', summary)
        self.assertIn('Performance', summary)


@override_settings(MEDIA_ROOT=str(Path(__file__).resolve().parent / 'test_media'))
class SiteAuditVisualTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='visualuser', password='pass12345')
        self.report = SiteAuditReport.objects.create(
            user=self.user,
            url='https://example.com',
            status=SiteAuditReport.STATUS_COMPLETED,
        )

    def test_visual_asset_model(self):
        expires = timezone.now() + timedelta(hours=24)
        asset = SiteAuditVisualAsset.objects.create(
            report=self.report,
            asset_id='abc123',
            file=f'site_audit/{self.report.pk}/abc123.avif',
            kind=SiteAuditVisualAsset.KIND_CROP,
            audit_id='color-contrast',
            strategy='mobile',
            expires_at=expires,
        )
        self.assertEqual(asset.report_id, self.report.pk)


class SiteAuditAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='audituser', password='pass12345')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.lead = Lead.objects.create(user=self.user, name='Loja Teste', website='https://example.com', source='manual')

    @patch('site_audit.views.run_full_audit')
    def test_run_audit_async_completes(self, mock_run):
        mock_run.return_value = {
            'scores': {'mobile': {'performance': 80}, 'desktop': {'performance': 90}},
            'core_web_vitals': {},
            'recommendations': {'mobile': {}, 'desktop': {}},
            'summary': 'OK',
        }
        report = SiteAuditReport.objects.create(
            user=self.user,
            url='https://example.com',
            status=SiteAuditReport.STATUS_PENDING,
        )
        from site_audit.views import _run_audit_async
        _run_audit_async(report.pk)
        report.refresh_from_db()
        self.assertEqual(report.status, SiteAuditReport.STATUS_COMPLETED)
        mock_run.assert_called_once_with('https://example.com', report_id=report.pk)

    @patch('site_audit.views.threading.Thread')
    def test_create_and_link_lead(self, mock_thread):
        report = SiteAuditReport.objects.create(
            user=self.user,
            lead=self.lead,
            url='https://example.com',
            status=SiteAuditReport.STATUS_COMPLETED,
            scores={'mobile': {'performance': 70}, 'desktop': {'performance': 85}},
        )
        r2 = self.client.post(f'/api/site-audits/{report.id}/link-lead/', {'lead_id': self.lead.id})
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()['lead'], self.lead.id)

        mock_thread.return_value.start.return_value = None
        r = self.client.post('/api/site-audits/', {'url': 'https://other.com', 'lead_id': self.lead.id})
        self.assertEqual(r.status_code, 201)
        mock_thread.assert_called_once()

    def test_history_period_filter(self):
        today = timezone.now()
        old = today - timedelta(days=10)
        r_old = SiteAuditReport.objects.create(user=self.user, url='https://old.com')
        SiteAuditReport.objects.filter(pk=r_old.pk).update(created_at=old)
        SiteAuditReport.objects.create(user=self.user, url='https://new.com')
        r = self.client.get('/api/site-audits/?period=7d')
        self.assertEqual(r.status_code, 200)
        urls = [x['url'] for x in r.json()]
        self.assertIn('https://new.com', urls)
        self.assertNotIn('https://old.com', urls)

    def test_history_date_range_filter(self):
        d = timezone.localdate() - timedelta(days=5)
        from datetime import datetime, time as dt_time
        created = timezone.make_aware(datetime.combine(d, dt_time(12, 0)))
        r1 = SiteAuditReport.objects.create(user=self.user, url='https://range.com')
        SiteAuditReport.objects.filter(pk=r1.pk).update(created_at=created)
        iso = d.isoformat()
        r = self.client.get(f'/api/site-audits/?date_from={iso}&date_to={iso}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)

    def test_export_markdown_json(self):
        report = SiteAuditReport.objects.create(
            user=self.user,
            lead=self.lead,
            url='https://example.com',
            status=SiteAuditReport.STATUS_COMPLETED,
            scores={'mobile': {'performance': 70, 'seo': 90}, 'desktop': {'performance': 85, 'seo': 92}},
            summary='Test summary',
            recommendations={'mobile': {'performance': [{'title': 'Fix LCP', 'severity': 'high'}]}},
        )
        md = audit_to_markdown(report)
        self.assertIn('Auditoria de Site', md)
        self.assertIn('Loja Teste', md)
        data = json.loads(audit_to_json(report))
        self.assertEqual(data['lead_name'], 'Loja Teste')


class CleanupVisualsCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cleanupuser', password='pass12345')
        self.report = SiteAuditReport.objects.create(
            user=self.user, url='https://example.com', status=SiteAuditReport.STATUS_COMPLETED,
        )

    def test_cleanup_removes_expired_assets(self):
        SiteAuditVisualAsset.objects.create(
            report=self.report,
            asset_id='expired1',
            file=f'site_audit/{self.report.pk}/expired1.avif',
            expires_at=timezone.now() - timedelta(hours=1),
        )
        from django.core.management import call_command
        call_command('cleanup_audit_visuals', verbosity=0)
        self.assertEqual(SiteAuditVisualAsset.objects.count(), 0)
