import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from ai import providers
from ai.service import AIUnavailable, busy_message, generate_reply
from chat.models import Conversation

User = get_user_model()


@override_settings(
    OPENAI_API_KEY='k1', OPENAI_MODEL='gpt-x', OPENAI_BASE_URL='https://openai.local/v1',
    GROQ_API_KEY='k2', GROQ_MODEL='groq-x', GROQ_BASE_URL='https://groq.local/v1',
    GEMINI_API_KEY='',
    AI_CLOUD_CHAIN=['openai', 'gemini', 'groq'],
    AI_CLOUD_FALLBACK_LOCAL=False,
)
class CloudChainTests(TestCase):
    def test_only_providers_with_keys_enter_chain(self):
        # gemini sem chave -> fica de fora; ordem openai depois groq.
        chain = providers.get_cloud_providers()
        self.assertEqual([p['name'] for p in chain], ['openai', 'groq'])

    def test_fallback_to_second_provider(self):
        def side_effect(provider, messages, options):
            if provider['name'] == 'openai':
                raise providers.ProviderError('falhou')
            return 'resposta do groq'

        with patch('ai.providers.call_openai_compatible', side_effect=side_effect):
            out = generate_reply([{'role': 'user', 'content': 'oi'}], mode='cloud')
        self.assertEqual(out, 'resposta do groq')

    def test_all_providers_fail_raises_unavailable(self):
        with patch('ai.providers.call_openai_compatible',
                   side_effect=providers.ProviderError('x')):
            with self.assertRaises(AIUnavailable):
                generate_reply([{'role': 'user', 'content': 'oi'}], mode='cloud')


@override_settings(AI_CLOUD_CHAIN=['openai'], OPENAI_API_KEY='', AI_CLOUD_FALLBACK_LOCAL=False)
class NoProviderTests(TestCase):
    def test_cloud_without_keys_raises(self):
        with self.assertRaises(AIUnavailable):
            generate_reply([{'role': 'user', 'content': 'oi'}], mode='cloud')


class LocalModeTests(TestCase):
    def test_local_uses_ollama(self):
        with patch('ai.providers.call_ollama', return_value='oi do ollama') as m:
            out = generate_reply([{'role': 'user', 'content': 'oi'}], mode='local')
        self.assertEqual(out, 'oi do ollama')
        m.assert_called_once()

    def test_local_failure_raises(self):
        with patch('ai.providers.call_ollama', side_effect=providers.ProviderError('down')):
            with self.assertRaises(AIUnavailable):
                generate_reply([{'role': 'user', 'content': 'oi'}], mode='local')


class BusyMessageTests(TestCase):
    def test_busy_message_is_human(self):
        msg = busy_message()
        self.assertTrue(msg)
        self.assertNotIn('⚠️', msg)


class ChatSendTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u', password='x', email='u@x.com')
        self.client.force_login(self.user)
        self.conv = Conversation.objects.create(user=self.user, title='Nova Conversa')

    @patch('chat.views.generate_reply', return_value='Olá! Como posso te ajudar? 😊')
    def test_send_message_returns_reply_and_persists_mode(self, _mock):
        resp = self.client.post(
            reverse('chat_send'),
            data=json.dumps({'conversation_id': self.conv.id, 'message': 'oi', 'ai_mode': 'cloud'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data['pending'])
        self.assertIn('Olá', data['reply'])
        # O toggle persiste o modo na conversa (feito na thread principal).
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.ai_mode, 'cloud')

    @patch('chat.views.generate_reply', side_effect=AIUnavailable('indisponível'))
    def test_send_message_shows_busy_on_failure(self, _mock):
        resp = self.client.post(
            reverse('chat_send'),
            data=json.dumps({'conversation_id': self.conv.id, 'message': 'oi'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data['pending'])
        # Mensagem humana de "ocupado", nunca um erro técnico.
        self.assertTrue(data['reply'])
        self.assertNotIn('⚠️', data['reply'])
