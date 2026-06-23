"""Camada de IA compartilhada (LLM) do Nuviie.

Usada tanto pelo Chat IA (`chat/`) quanto pelo WhatsApp (`whatsapp/`).
Suporta dois modos, escolhidos por toggle:

- ``cloud``: provedores de nuvem compatíveis com o formato OpenAI
  (GPT/OpenAI -> Gemini -> Groq -> ...), tentados em cadeia de fallback.
- ``local``: modelo local via Ollama.

Não é um app Django (sem models/migrations) — é só um pacote importável.
"""
