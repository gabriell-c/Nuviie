"""Serviço de IA compartilhado: escolhe o modo (nuvem/local) e gera a resposta.

- ``cloud``: tenta os provedores de nuvem em cadeia (fallback) e retorna o 1o que
  responder. Se todos falharem -> ``AIUnavailable``.
- ``local``: usa o Ollama. Se falhar -> ``AIUnavailable``.

O toggle (nuvem x local) é uma ESCOLHA, não um fallback. Quando tudo falha, o
chamador deve mostrar uma mensagem humana de "ocupado" (`busy_message()`), nunca
um erro técnico.
"""
import logging
import random
import time

from django.conf import settings

from . import providers

logger = logging.getLogger('ai')


class AIUnavailable(Exception):
    """Nenhum provedor conseguiu gerar uma resposta."""


# Mensagens humanas de "espera" — usadas quando a IA está indisponível, para que o
# cliente não perceba que houve uma falha técnica.
BUSY_MESSAGES = [
    "Opa! Deixa eu ver isso com calma aqui, me dá só um minutinho? 🙏",
    "Tô finalizando um atendimento rapidinho, já já te respondo certinho! 😊",
    "Aqui tá meio corrido agora por causa da demanda — me dá 1 minuto que eu já volto pra te responder. 🙏",
    "Só um instantinho que eu já te respondo direitinho! 😊",
    "Peraí que eu já te dou um retorno completo, tá? Não vou demorar. 🙏",
]


def busy_message():
    """Sorteia uma mensagem humana de espera (usada quando a IA falha)."""
    return random.choice(BUSY_MESSAGES)


def resolve_mode(mode):
    """Normaliza o modo. 'default'/None -> AI_DEFAULT_MODE (padrão: 'local')."""
    if mode in ('cloud', 'local'):
        return mode
    return getattr(settings, 'AI_DEFAULT_MODE', 'local')


def generate_reply(messages, *, mode='default', options=None):
    """Gera uma resposta da IA. Retorna texto ou levanta ``AIUnavailable``.

    `messages`: lista [{role, content}] já montada pelo chamador (sem prefixos
    específicos de provedor — isso é tratado em `providers`).
    """
    options = options or {}
    mode = resolve_mode(mode)

    if mode == 'local':
        return _generate_local(messages, options)

    # Modo nuvem: cadeia de fallback entre provedores.
    try:
        return _generate_cloud(messages, options)
    except AIUnavailable:
        # Por padrão, NÃO cai para o local (o toggle é uma escolha, não fallback).
        # Pode ser ligado via AI_CLOUD_FALLBACK_LOCAL=true para quem quiser.
        if getattr(settings, 'AI_CLOUD_FALLBACK_LOCAL', False):
            logger.info('Cadeia de nuvem indisponível; tentando LLM local (fallback opcional).')
            return _generate_local(messages, options)
        raise


def _generate_cloud(messages, options):
    chain = providers.get_cloud_providers()
    if not chain:
        logger.warning(
            'Modo nuvem selecionado, mas nenhum provedor está configurado '
            '(defina ao menos OPENAI_API_KEY / GEMINI_API_KEY / GROQ_API_KEY).'
        )
        raise AIUnavailable('nenhum provedor de nuvem configurado')

    for provider in chain:
        started = time.monotonic()
        try:
            text = providers.call_openai_compatible(provider, messages, options)
            logger.info(
                'IA nuvem OK via %s (%s) em %.1fs',
                provider['name'], provider['model'], time.monotonic() - started,
            )
            return text
        except Exception as exc:
            logger.warning(
                'IA nuvem falhou via %s (%s) em %.1fs: %s — tentando próximo provedor',
                provider['name'], provider['model'], time.monotonic() - started, exc,
            )
            continue

    raise AIUnavailable('todos os provedores de nuvem falharam')


def _generate_local(messages, options):
    started = time.monotonic()
    try:
        text = providers.call_ollama(messages, options)
        logger.info('IA local (Ollama) OK em %.1fs', time.monotonic() - started)
        return text
    except Exception as exc:
        logger.warning('IA local (Ollama) falhou em %.1fs: %s', time.monotonic() - started, exc)
        raise AIUnavailable(f'ollama indisponível: {exc}')
