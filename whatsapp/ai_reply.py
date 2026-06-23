"""Atendente IA no WhatsApp: auto-resposta (opt-in) e rascunho assistido.

Reaproveita a camada `ai` (modo nuvem/local por número) e o mesmo `SYSTEM_PROMPT`
do Chat IA, montando o contexto a partir do histórico de `WhatsAppMessage`.
"""
import logging
import random
import threading
import time

from ai.service import AIUnavailable, generate_reply
from chat.views import SYSTEM_PROMPT

logger = logging.getLogger('ai')

# Quantas mensagens recentes (in/out) entram no contexto do modelo.
MAX_HISTORY = 16


def build_messages(user, phone):
    """Monta [{role, content}] = system + histórico recente daquele telefone."""
    from .models import WhatsAppMessage

    rows = list(
        WhatsAppMessage.objects
        .filter(user=user, phone=phone, message_type='text')
        .exclude(text='')
        .order_by('-created_at')
        .values_list('direction', 'text')[:MAX_HISTORY]
    )
    rows.reverse()

    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    for direction, text in rows:
        role = 'user' if direction == 'in' else 'assistant'
        messages.append({'role': role, 'content': text})
    return messages


def generate_draft(user, inst, phone):
    """Gera um rascunho de resposta (não envia). Levanta AIUnavailable se falhar."""
    messages = build_messages(user, phone)
    mode = getattr(inst, 'ai_mode', 'default') if inst else 'default'
    return generate_reply(
        messages, mode=mode, options={'temperature': 0.7, 'max_tokens': 320},
    )


def autoreply_async(user, inst, phone, *, lead=None):
    """Gera e ENVIA a auto-resposta em background (não bloqueia o webhook).

    Aplica um jitter humano antes de responder e, se a IA estiver indisponível,
    simplesmente não responde (sem mandar erro técnico para o cliente).
    """
    def _run():
        try:
            time.sleep(random.uniform(2.0, 6.0))  # parece humano + agrega msgs em sequência
            text = generate_draft(user, inst, phone)
        except AIUnavailable as exc:
            logger.info('Auto-resposta WhatsApp adiada (IA indisponível) p/ %s: %s', phone, exc)
            return
        except Exception:
            logger.exception('Falha ao gerar auto-resposta WhatsApp p/ %s', phone)
            return

        if not text:
            return

        try:
            from .services import dispatch_text
            msg = dispatch_text(user, inst, phone, text, lead=lead)
            if msg.status == 'failed':
                logger.warning('Auto-resposta WhatsApp não enviada p/ %s: %s', phone, msg.error)
        except Exception:
            logger.exception('Falha ao enviar auto-resposta WhatsApp p/ %s', phone)

    threading.Thread(target=_run, daemon=True).start()
