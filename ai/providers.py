"""Provedores de LLM: nuvem (compatível com OpenAI) e local (Ollama).

GPT/OpenAI, Gemini e Groq expõem o mesmo formato de API da OpenAI
(`POST {base_url}/chat/completions`), então um único cliente HTTP atende os três
(e qualquer outro provedor compatível). O Ollama usa o endpoint nativo dele.

Tudo via `requests` — sem SDK extra.
"""
import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger('ai')

_THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL)

# Sessão com pool de conexões reaproveitada por todas as chamadas.
_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=16, max_retries=0)
_session.mount('http://', _adapter)
_session.mount('https://', _adapter)

# Defaults por provedor de nuvem (base_url no formato OpenAI + modelo sugerido).
# Os modelos são apenas padrões — ajuste via env para o que sua conta tem acesso.
CLOUD_DEFAULTS = {
    'openai': {
        'base_url': 'https://api.openai.com/v1',
        'model': 'gpt-4o-mini',
    },
    'gemini': {
        'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai',
        'model': 'gemini-1.5-flash',
    },
    'groq': {
        'base_url': 'https://api.groq.com/openai/v1',
        'model': 'llama-3.3-70b-versatile',
    },
}


class ProviderError(Exception):
    """Falha ao chamar um provedor específico."""


def _strip_think(text):
    return _THINK_RE.sub('', text or '').strip()


def _cfg(name, key, default=''):
    return getattr(settings, f'{name.upper()}_{key}', default)


def get_cloud_providers():
    """Retorna a cadeia ordenada de provedores de nuvem habilitados (com API key).

    A ordem vem de ``AI_CLOUD_CHAIN``. Só entram os provedores que têm chave +
    base_url + modelo resolvidos.
    """
    chain = getattr(settings, 'AI_CLOUD_CHAIN', ['openai', 'gemini', 'groq'])
    providers = []
    for raw in chain:
        name = (raw or '').strip().lower()
        if not name:
            continue
        api_key = _cfg(name, 'API_KEY', '')
        if not api_key:
            continue
        defaults = CLOUD_DEFAULTS.get(name, {})
        base_url = (_cfg(name, 'BASE_URL', '') or defaults.get('base_url', '')).rstrip('/')
        model = _cfg(name, 'MODEL', '') or defaults.get('model', '')
        if not base_url or not model:
            logger.warning('Provedor de IA "%s" ignorado: base_url/model ausentes.', name)
            continue
        providers.append({
            'name': name,
            'base_url': base_url,
            'api_key': api_key,
            'model': model,
        })
    return providers


def call_openai_compatible(provider, messages, options):
    """Chama um provedor no formato OpenAI (`/chat/completions`). Levanta ProviderError."""
    url = f"{provider['base_url']}/chat/completions"
    headers = {
        'Authorization': f"Bearer {provider['api_key']}",
        'Content-Type': 'application/json',
    }
    payload = {
        'model': provider['model'],
        'messages': messages,
        'temperature': options.get('temperature', 0.7),
        'max_tokens': options.get('max_tokens', 320),
        'stream': False,
    }
    timeout = options.get('timeout') or getattr(settings, 'AI_HTTP_TIMEOUT', 60)
    try:
        resp = _session.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise ProviderError(str(exc)) from exc
    except ValueError as exc:
        raise ProviderError(f'resposta não-JSON: {exc}') from exc

    choices = data.get('choices') or []
    if not choices:
        raise ProviderError('resposta sem "choices"')
    content = (choices[0].get('message') or {}).get('content', '')
    text = _strip_think(content)
    if not text:
        raise ProviderError('conteúdo vazio')
    return text


def call_ollama(messages, options):
    """Chama o Ollama local (endpoint nativo). Levanta ProviderError.

    Aplica o prefixo `/no_think` nas mensagens do usuário (controle do Qwen para
    suprimir o chain-of-thought) — algo específico do Ollama, por isso fica aqui.
    """
    url = getattr(settings, 'OLLAMA_URL', 'http://localhost:11434/api/chat')
    model = getattr(settings, 'OLLAMA_MODEL', 'qwen2.5:7b')

    prepared = []
    for m in messages:
        if m.get('role') == 'user':
            prepared.append({'role': 'user', 'content': f"/no_think {m.get('content', '')}"})
        else:
            prepared.append({'role': m.get('role'), 'content': m.get('content', '')})

    payload = {
        'model': model,
        'messages': prepared,
        'stream': False,
        'think': False,
        'options': {
            'num_ctx': options.get('num_ctx', 8192),
            'num_predict': options.get('max_tokens', 320),
            'temperature': options.get('temperature', 0.7),
            'repeat_penalty': options.get('repeat_penalty', 1.1),
            'top_p': options.get('top_p', 0.9),
        },
    }
    timeout = options.get('timeout') or getattr(settings, 'AI_HTTP_TIMEOUT_LOCAL', 180)
    try:
        resp = _session.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise ProviderError(str(exc)) from exc
    except ValueError as exc:
        raise ProviderError(f'resposta não-JSON: {exc}') from exc

    content = (data.get('message') or {}).get('content', '')
    text = _strip_think(content)
    if not text:
        raise ProviderError('conteúdo vazio')
    return text
