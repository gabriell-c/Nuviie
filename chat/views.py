import json
import logging
import threading

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone

from ai.service import AIUnavailable, busy_message, generate_reply

from .models import Conversation, Message

logger = logging.getLogger(__name__)

VALID_AI_MODES = ('default', 'cloud', 'local')

SLOW_RESPONSE_THRESHOLD = 90
PROVISIONAL_REPLY = "Deixa eu verificar isso direitinho pra te dar a melhor resposta 😊"

SYSTEM_PROMPT = """Você é a Júlia, do time da Nuviie — agência que faz sites, landing pages, sistemas e automações. Você atende pelo WhatsApp como uma pessoa de verdade: calma, atenciosa e direta. Você é a ESPECIALISTA: o cliente quase nunca sabe o que precisa, então quem descobre e RECOMENDA a solução é você.

REGRAS DE OURO (sempre):
1. Mensagens curtas. 1 ou 2 frases, quase sempre. Muitas vezes uma linha só. Nunca um textão.
2. NUNCA use emoji.
3. No máximo UMA pergunta por mensagem. Às vezes nem pergunte, só responda.
4. Fale simples, como gente no WhatsApp. Proibido jargão (UX, conversão, integração, automação, CRO) a não ser que o cliente use primeiro.
5. Você decide a solução. NUNCA pergunte "que tipo de site você quer?" — descubra o negócio e recomende você mesma.

COMO CONDUZIR:
Você é a especialista, então guie a conversa. Primeiro entenda o negócio com perguntas simples, uma de cada vez:
- "O que você vende / faz?"
- "Como seus clientes te encontram hoje?"
- "Você já tem Instagram, site, aparece no Google?"
- "As pessoas te procuram e não acham, ou acham e não compram?"
Depois de entender o básico, PARE de perguntar e RECOMENDE com convicção, em linguagem simples: "Pro seu caso, o que mais traz cliente é X, porque Y."

GUIA DE DECISÃO (uso interno — não recite isto, use pra escolher o que recomendar):
- Negócio local (loja, clínica, salão, oficina) querendo mais cliente -> site profissional que apareça no Google + presença no Instagram.
- Vende pela internet / roda anúncio -> landing page focada em vender, rápida e convincente.
- Faz tudo manual (caderno, WhatsApp, planilha) -> sistema ou automação pra organizar e ganhar tempo.
- Só quer passar profissionalismo / ter o próprio espaço -> site institucional bem feito.
Serviços que existem (use só estes): sites institucionais, landing pages, sistemas web, automações, soluções com IA, integrações, projetos personalizados.

CONECTE DE VERDADE:
- Reaja ao que a pessoa disse, com as palavras dela. Ex.: "minha página tá feia e não vende" -> "Entendi, então o problema nem é ter a página, é que ela não tá te trazendo venda, né?"
- Não seja animadora de torcida: proibido começar quase toda mensagem com "Perfeito/Legal/Entendi/Ótimo/Que bom".
- Traduza tudo em ganho real: mais cliente, mais venda, menos trabalho à toa.

LEMBRE O QUE JÁ ROLOU:
- Se a pessoa disse que já fez algo (já preencheu o formulário, já tem site, já mandou os dados), NUNCA peça de novo.
- Nunca repita uma frase ou pergunta que você já mandou. Use o nome e o contexto da pessoa.

OBJEÇÕES (acolha, curto):
- "Tá caro": é investimento que se paga; pergunte que valor ela tinha em mente.
- "Acho mais barato": foque no resultado e no risco de refazer.
- "Vou pensar": respeite e descubra com leveza a dúvida real.
- "Não tenho tempo": proponha um passo pequeno.
- Não é o decisor: descubra com jeito quem decide e vire essa pessoa sua aliada.

PREÇO E PRAZO: nunca invente. Dependem do escopo e saem na proposta, depois do briefing.

FECHAMENTO: quando houver interesse real (ou pedirem orçamento), mande o link UMA vez só, com um resumo de uma linha:
"Pelo que você me contou, é [resumo numa linha]. Pra equipe montar sua proposta, é só preencher esse formulário rapidinho: https://forms.gle/qeDyZ8mx6ZgRAvaJA"
Depois do link, não fique perguntando nem reenviando.

EXEMPLOS (siga esse ritmo: curto, sem emoji, você liderando):

Cliente: oi, vocês fazem site?
Júlia: Oi! Aqui é a Júlia, da Nuviie. Fazemos sim. Me conta rapidinho: é pra qual tipo de negócio?

Cliente: queria mais clientes pro meu negócio
Júlia: Boa, é o que a gente mais resolve por aqui. O que você faz / vende?
Cliente: tenho uma barbearia
Júlia: Show. E hoje, como seus clientes costumam te achar? Instagram, indicação, Google?
Cliente: mais indicação mesmo, não tenho quase nada online
Júlia: Entendi. Então tá vindo cliente, mas você depende de boca a boca e perde quem te procura no Google e não acha.
Júlia: Pro seu caso, o que mais traz cliente novo é um site simples que apareça no Google quando procuram barbearia na sua região, junto com o Instagram organizado. É por aí que eu iria.

Cliente: minha landing tá feia e não vende
Júlia: Saquei. Então o problema nem é ter a página, é que ela não tá te trazendo venda. Você roda anúncio pra ela?
Cliente: rodo
Júlia: Então o caminho é uma landing nova, rápida e feita pra converter quem vem do anúncio. Eu cuido disso do começo ao fim.

Cliente: achei meio caro
Júlia: Te entendo. A ideia é que se pague: uma página que vende mais costuma valer bem mais do que custou. Qual valor você tinha em mente? Aí eu alinho certinho.

Cliente: pronto, já preenchi
Júlia: Show, já recebi por aqui. O time vai dar uma olhada e te chama pra seguir, combinado?

ANTES DE ENVIAR, confira: está curto? sem emoji? no máximo 1 pergunta? você recomendou a solução em vez de jogar a decisão pro cliente?
"""

_SYSTEM_MSG = {"role": "system", "content": SYSTEM_PROMPT}

# Lembrete curto injetado como ÚLTIMA mensagem antes de gerar. Modelo pequeno
# "esquece" regras do topo quando o histórico cresce; a recência reforça o essencial.
TURN_REMINDER = (
    "Lembrete: responda como a Júlia. No máximo 1 ou 2 frases curtas. SEM emoji. "
    "No máximo UMA pergunta. Se você já entende o negócio da pessoa, RECOMENDE você "
    "mesma a melhor solução com convicção — não pergunte que tipo de site ela quer."
)
_REMINDER_MSG = {"role": "system", "content": TURN_REMINDER}

MAX_HISTORY_MESSAGES = 16
# A cada SUMMARY_CHUNK mensagens antigas "saídas" da janela recente, atualizamos o resumo.
SUMMARY_CHUNK = 8

SUMMARY_SYSTEM_PROMPT = (
    "Você é um assistente que mantém a MEMÓRIA de longo prazo de uma conversa de "
    "vendas pelo WhatsApp entre um atendente da Nuviie e um cliente. Sua tarefa é "
    "produzir/atualizar um resumo conciso e factual, em português do Brasil, que o "
    "atendente vai reler para lembrar do cliente nas próximas mensagens.\n\n"
    "Capture e mantenha apenas o que importa: nome do cliente, nome/tipo do negócio, "
    "nicho, cidade, problemas e dores mencionados, orçamento/limitações, preferências, "
    "objeções levantadas, o que já foi oferecido/combinado, e próximos passos. "
    "Se a pessoa não é o decisor, registre isso.\n\n"
    "Regras: reescreva um resumo único e atualizado (não acumule repetições), use no "
    "máximo ~180 palavras, tópicos curtos, sem floreio e sem inventar nada que não "
    "esteja nas mensagens. Não inclua saudações nem comentários — só o resumo."
)

def _build_messages(conversation):
    """Monta o contexto: system + resumo de longo prazo + mensagens recentes.

    Tudo que já foi consolidado em `summary` (as `summary_message_count` mensagens
    mais antigas) sai da janela recente, mantendo o contexto enxuto mas com memória.
    As mensagens saem "limpas" (role/content) — prefixos específicos de provedor
    (ex.: `/no_think` do Ollama) são aplicados na camada `ai`.
    """
    covered = conversation.summary_message_count or 0
    rows = list(
        conversation.messages
        .order_by('created_at')
        .values_list('role', 'content')
    )
    recent = rows[covered:]

    history = [{"role": role, "content": content} for role, content in recent]

    messages = [_SYSTEM_MSG]
    summary = (conversation.summary or '').strip()
    if summary:
        messages.append({
            "role": "system",
            "content": (
                "MEMÓRIA DA CONVERSA (resumo do que já foi conversado antes — "
                "use para lembrar do cliente, não repita perguntas já respondidas):\n"
                + summary
            ),
        })
    # Lembrete por último (efeito recência): logo antes da geração.
    return messages + history + [_REMINDER_MSG]


def _maybe_summarize(conversation):
    """Consolida mensagens antigas no resumo quando a janela recente cresce demais.

    Roda de forma incremental e idempotente: só atualiza quando há pelo menos
    SUMMARY_CHUNK mensagens novas a consolidar, evitando chamadas desnecessárias.
    """
    rows = list(
        conversation.messages
        .order_by('created_at')
        .values_list('role', 'content')
    )
    total = len(rows)
    target = max(0, total - MAX_HISTORY_MESSAGES)
    covered = conversation.summary_message_count or 0

    if target - covered < SUMMARY_CHUNK:
        return

    to_fold = rows[covered:target]
    convo_text = "\n".join(
        f"{'Cliente' if role == 'user' else 'Atendente'}: {content}"
        for role, content in to_fold
    )

    previous = (conversation.summary or '').strip()
    user_parts = []
    if previous:
        user_parts.append("Resumo atual:\n" + previous)
    user_parts.append("Novas mensagens a incorporar:\n" + convo_text)
    user_parts.append("Reescreva o resumo atualizado (único, conciso).")

    summary_messages = [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]

    try:
        new_summary = generate_reply(
            summary_messages,
            mode=conversation.ai_mode,
            options={"temperature": 0.3, "max_tokens": 280},
        )
    except AIUnavailable:
        logger.info("Resumo da conversa adiado: IA indisponível.")
        return

    new_summary = (new_summary or '').strip()
    if not new_summary:
        return

    conversation.summary = new_summary
    conversation.summary_message_count = target
    conversation.save(update_fields=['summary', 'summary_message_count'])


def _auto_title(conversation):
    row = (
        conversation.messages
        .filter(role='user')
        .order_by('created_at')
        .values_list('content', flat=True)[:1]
    )
    if row:
        text = row[0]
        conversation.title = text[:50] + ('...' if len(text) > 50 else '')
        conversation.save(update_fields=['title'])


def _generate_chat_reply(conversation, messages):
    """Gera a resposta do atendente via camada `ai` (nuvem/local conforme a conversa).

    Retorna (texto, erro). Em qualquer falha, `texto` é None e `erro` é 'unavailable'
    — o chamador então usa uma mensagem humana de "ocupado", nunca um erro técnico.
    """
    try:
        text = generate_reply(
            messages,
            mode=conversation.ai_mode,
            options={"temperature": 0.5, "max_tokens": 150},
        )
        return (text or '').strip(), None
    except AIUnavailable as exc:
        logger.warning("Atendente IA indisponível: %s", exc)
        return None, "unavailable"


def _save_assistant_message(conversation, content):
    msg = Message.objects.create(
        conversation=conversation,
        role='assistant',
        content=content,
    )
    Conversation.objects.filter(pk=conversation.pk).update(
        updated_at=timezone.now()
    )
    return msg


@login_required
def chat_home(request):
    conversations = Conversation.objects.filter(
        user=request.user
    ).order_by('-updated_at')

    conversation_id = request.GET.get('conv')
    if conversation_id:
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
    else:
        conversation = conversations.first()
        if not conversation:
            conversation = Conversation.objects.create(user=request.user)

    messages_qs = (
        conversation.messages
        .only('role', 'content', 'created_at')
        .order_by('created_at')
    )

    return render(request, 'chat/chat.html', {
        'conversations': conversations,
        'active_conversation': conversation,
        'messages': messages_qs,
    })


@login_required
@require_POST
def new_conversation(request):
    conv = Conversation.objects.create(user=request.user, title='Nova Conversa')
    return JsonResponse({'id': conv.id, 'title': conv.title, 'ai_mode': conv.ai_mode})


@login_required
@require_POST
def delete_conversation(request, conv_id):
    conv = get_object_or_404(Conversation, id=conv_id, user=request.user)
    conv.delete()
    return JsonResponse({'ok': True})


@login_required
@require_GET
def list_conversations(request):
    convs = list(
        Conversation.objects.filter(user=request.user)
        .order_by('-updated_at')
        .values('id', 'title', 'updated_at')
    )
    data = [
        {
            'id': c['id'],
            'title': c['title'],
            'updated_at': c['updated_at'].strftime('%d/%m %H:%M'),
        }
        for c in convs
    ]
    return JsonResponse({'conversations': data})


@login_required
@require_GET
def load_messages(request, conv_id):
    conv = get_object_or_404(Conversation, id=conv_id, user=request.user)
    msgs = (
        conv.messages
        .only('role', 'content', 'created_at')
        .order_by('created_at')
        .values('role', 'content', 'created_at')
    )
    data = [
        {
            'role': m['role'],
            'content': m['content'],
            'time': m['created_at'].strftime('%H:%M'),
        }
        for m in msgs
    ]
    return JsonResponse({'messages': data, 'title': conv.title, 'ai_mode': conv.ai_mode})


@login_required
@require_GET
def poll_response(request, conv_id):
    """Retorna a última mensagem do assistente após um ID informado."""
    conv = get_object_or_404(Conversation, id=conv_id, user=request.user)
    after_id = request.GET.get('after')

    qs = conv.messages.filter(role='assistant').order_by('-created_at')
    if after_id:
        try:
            qs = qs.filter(id__gt=int(after_id))
        except (TypeError, ValueError):
            pass

    msg = qs.first()
    if not msg:
        return JsonResponse({'ready': False})

    if msg.content == PROVISIONAL_REPLY:
        return JsonResponse({'ready': False})

    return JsonResponse({
        'ready': True,
        'reply': msg.content,
        'message_id': msg.id,
        'time': msg.created_at.strftime('%H:%M'),
        'title': conv.title,
    })


@login_required
@require_POST
def send_message(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    conv_id = data.get('conversation_id')
    user_text = data.get('message', '').strip()
    ai_mode = data.get('ai_mode')

    if not user_text:
        return JsonResponse({'error': 'Mensagem vazia'}, status=400)

    conversation = get_object_or_404(Conversation, id=conv_id, user=request.user)

    # Persiste o modo escolhido no toggle (nuvem x local), se válido.
    if ai_mode in VALID_AI_MODES and ai_mode != conversation.ai_mode:
        conversation.ai_mode = ai_mode
        conversation.save(update_fields=['ai_mode'])

    Message.objects.create(
        conversation=conversation,
        role='user',
        content=user_text,
    )

    last_assistant_id = (
        conversation.messages
        .filter(role='assistant')
        .order_by('-id')
        .values_list('id', flat=True)
        .first()
    )

    chat_messages = _build_messages(conversation)
    result_holder = {"ai_text": None, "error": None, "done": False}

    def _run():
        ai_text, error = _generate_chat_reply(conversation, chat_messages)
        result_holder["ai_text"] = ai_text
        result_holder["error"] = error
        result_holder["done"] = True

        if ai_text:
            try:
                _save_assistant_message(conversation, ai_text)
            except Exception:
                logger.exception("Falha ao salvar resposta do assistente")
            try:
                _maybe_summarize(conversation)
            except Exception:
                logger.exception("Falha ao atualizar memória da conversa")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=SLOW_RESPONSE_THRESHOLD)

    is_new_conversation = conversation.title == 'Nova Conversa'

    if result_holder["done"]:
        ai_text = result_holder["ai_text"]
        error = result_holder["error"]

        if not ai_text and error:
            ai_text = busy_message()
            _save_assistant_message(conversation, ai_text)

        if is_new_conversation:
            _auto_title(conversation)
            conversation.refresh_from_db(fields=['title'])

        return JsonResponse({
            'reply': ai_text,
            'title': conversation.title,
            'time': timezone.localtime().strftime('%H:%M'),
            'pending': False,
            'last_assistant_id': last_assistant_id,
        })

    provisional_msg = _save_assistant_message(conversation, PROVISIONAL_REPLY)

    if is_new_conversation:
        _auto_title(conversation)
        conversation.refresh_from_db(fields=['title'])

    return JsonResponse({
        'reply': PROVISIONAL_REPLY,
        'title': conversation.title,
        'time': timezone.localtime().strftime('%H:%M'),
        'pending': True,
        'last_assistant_id': provisional_msg.id,
    })
