import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from leads.models import Lead

from .models import WhatsAppInstance, WhatsAppMessage
from .services import find_lead_by_phone, jid_to_phone, normalize_number, store_incoming_message

User = get_user_model()


class HelpersTests(TestCase):
    def test_normalize_number(self):
        self.assertEqual(normalize_number('+55 (11) 99999-9999'), '5511999999999')
        self.assertEqual(normalize_number(None), '')

    def test_jid_to_phone(self):
        self.assertEqual(jid_to_phone('5511999999999@s.whatsapp.net'), '5511999999999')
        self.assertEqual(jid_to_phone('5511999999999:12@s.whatsapp.net'), '5511999999999')

    def test_find_lead_by_phone_tolerates_ddi(self):
        user = User.objects.create_user(username='u1', password='x')
        lead = Lead.objects.create(user=user, name='Lead', source='manual',
                                   normalized_phone='5511988887777')
        self.assertEqual(find_lead_by_phone(user, '5511988887777'), lead)
        self.assertEqual(find_lead_by_phone(user, '11988887777'), lead)


class WebhookTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin', password='x')
        self.inst = WhatsAppInstance.objects.create(
            user=self.user, name='Comercial', instance_name='nuviie-1', status='connected',
        )
        self.lead = Lead.objects.create(
            user=self.user, name='Cliente', source='manual', normalized_phone='5511988887777',
        )

    def _payload(self):
        return {
            'event': 'messages.upsert',
            'instance': 'nuviie-1',
            'data': {
                'key': {'remoteJid': '5511988887777@s.whatsapp.net', 'fromMe': False, 'id': 'MSG1'},
                'pushName': 'Cliente',
                'message': {'conversation': 'Olá, tenho interesse!'},
                'messageTimestamp': 1700000000,
            },
        }

    @override_settings(WHATSAPP_WEBHOOK_TOKEN='secret-token')
    def test_webhook_stores_incoming_and_links_lead(self):
        resp = self.client.post(
            reverse('whatsapp_webhook'),
            data=json.dumps(self._payload()),
            content_type='application/json',
            HTTP_AUTHORIZATION='Bearer secret-token',
        )
        self.assertEqual(resp.status_code, 200)
        msg = WhatsAppMessage.objects.get(evolution_id='MSG1')
        self.assertEqual(msg.direction, 'in')
        self.assertEqual(msg.text, 'Olá, tenho interesse!')
        self.assertEqual(msg.lead, self.lead)

    @override_settings(WHATSAPP_WEBHOOK_TOKEN='secret-token')
    def test_webhook_rejects_bad_token(self):
        resp = self.client.post(
            reverse('whatsapp_webhook'),
            data=json.dumps(self._payload()),
            content_type='application/json',
            HTTP_AUTHORIZATION='Bearer wrong',
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(WhatsAppMessage.objects.count(), 0)

    @override_settings(WHATSAPP_WEBHOOK_TOKEN='secret-token')
    def test_webhook_ignores_fromme(self):
        payload = self._payload()
        payload['data']['key']['fromMe'] = True
        resp = self.client.post(
            reverse('whatsapp_webhook'),
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION='Bearer secret-token',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(WhatsAppMessage.objects.count(), 0)

    def test_store_incoming_dedupes(self):
        data = self._payload()['data']
        m1, c1 = store_incoming_message(user=self.user, instance=self.inst, payload_data=data)
        m2, c2 = store_incoming_message(user=self.user, instance=self.inst, payload_data=data)
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(m1.id, m2.id)


class SendTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin', password='x')
        self.client.force_login(self.user)
        self.inst = WhatsAppInstance.objects.create(
            user=self.user, name='Comercial', instance_name='nuviie-1',
            status='connected', is_default=True,
            api_url='http://evo.local', api_key='k',
        )
        self.lead = Lead.objects.create(
            user=self.user, name='Cliente', source='manual', normalized_phone='5511988887777',
        )

    @patch('whatsapp.views.EvolutionClient.send_text')
    def test_send_creates_outgoing_message(self, mock_send):
        mock_send.return_value = {'key': {'id': 'OUT1'}}
        resp = self.client.post(
            reverse('whatsapp-message-send'),
            data=json.dumps({'lead': self.lead.id, 'text': 'Oi!'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        msg = WhatsAppMessage.objects.get(evolution_id='OUT1')
        self.assertEqual(msg.direction, 'out')
        self.assertEqual(msg.status, 'sent')
        self.assertEqual(msg.lead, self.lead)
        mock_send.assert_called_once()
