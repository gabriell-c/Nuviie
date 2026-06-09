#!/usr/bin/env python3
"""
Rode no terminal para diagnosticar a velocidade do Ollama:
    python3 testar_ollama.py

Testa 3 configurações em sequência e mostra qual é mais rápida.
Não precisa do Django instalado.
"""

import requests
import time
import json

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b"

SYSTEM_PROMPT_CURTO = "Você é um atendente comercial da Nuviie. Responda de forma curta e amigável, como no WhatsApp."

SYSTEM_PROMPT_ORIGINAL = """Você é um atendente comercial da Nuviie, uma agência especializada em criação de sites profissionais, sistemas web, automações e soluções digitais para empresas.
[... prompt completo com ~1300 tokens ...]"""

def testar(label, payload):
    print(f"\n{'='*50}")
    print(f"TESTE: {label}")
    print(f"{'='*50}")
    inicio = time.time()
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=120)
        r.raise_for_status()
        fim = time.time()
        resultado = r.json()
        texto = resultado.get('message', {}).get('content', '').strip()
        duracao = fim - inicio
        tokens_gerados = len(texto.split())
        print(f"  Tempo:          {duracao:.1f}s")
        print(f"  Palavras:       {tokens_gerados}")
        print(f"  Tokens/s est.:  {tokens_gerados / duracao:.1f}")
        print(f"  Resposta:       {texto[:120]}{'...' if len(texto) > 120 else ''}")
        return duracao
    except requests.exceptions.ConnectionError:
        print("  ERRO: Ollama não está rodando! Execute: ollama serve")
        return None
    except requests.exceptions.Timeout:
        print("  ERRO: Timeout depois de 120s")
        return None
    except Exception as e:
        print(f"  ERRO: {e}")
        return None

# ── Teste 1: configuração original (igual ao seu views.py atual)
t1 = testar(
    "Original (num_ctx=2048, sem num_predict)",
    {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_ORIGINAL},
            {"role": "user", "content": "bom dia"}
        ],
        "stream": False,
        "options": {
            "thinking": False,
            "num_ctx": 2048,
        }
    }
)

# ── Teste 2: CONFIGURAÇÃO OTIMIZADA (igual ao novo views_optimized.py)
t2 = testar(
    "Otimizado (num_ctx=4096, num_predict=300)",
    {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_ORIGINAL},
            {"role": "user", "content": "bom dia"}
        ],
        "stream": False,
        "options": {
            "thinking": False,
            "num_ctx": 4096,
            "num_predict": 300,
            "temperature": 0.7,
            "repeat_penalty": 1.1,
            "top_p": 0.9,
        }
    }
)

# ── Teste 3: sem system prompt (para isolar o overhead)
t3 = testar(
    "Sem system prompt (baseline puro do modelo)",
    {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "bom dia"}
        ],
        "stream": False,
        "options": {
            "thinking": False,
            "num_ctx": 2048,
            "num_predict": 80,
        }
    }
)

# ── Teste 4: verifica se o modelo está na memória (GPU/RAM)
print(f"\n{'='*50}")
print("DIAGNÓSTICO DO SISTEMA")
print(f"{'='*50}")
try:
    r = requests.get("http://localhost:11434/api/tags", timeout=5)
    modelos = r.json().get('models', [])
    for m in modelos:
        if MODEL in m.get('name', ''):
            size_gb = m.get('size', 0) / 1e9
            print(f"  Modelo encontrado: {m['name']}")
            print(f"  Tamanho: {size_gb:.1f} GB")
            details = m.get('details', {})
            print(f"  Parâmetros: {details.get('parameter_size', 'N/A')}")
            print(f"  Quantização: {details.get('quantization_level', 'N/A')}")
except Exception as e:
    print(f"  Não foi possível obter info dos modelos: {e}")

try:
    r = requests.get("http://localhost:11434/api/ps", timeout=5)
    running = r.json().get('models', [])
    if running:
        print(f"\n  Modelos carregados na memória:")
        for m in running:
            print(f"    - {m.get('name')} | VRAM: {m.get('size_vram',0)//1e6:.0f}MB | RAM: {m.get('size',0)//1e6:.0f}MB")
    else:
        print("\n  AVISO: Nenhum modelo carregado na memória agora.")
        print("  O próximo request vai carregar o modelo do disco (lento).")
        print("  Dica: rode 'ollama run qwen3.5:4b' uma vez para manter na memória.")
except Exception as e:
    print(f"  Não foi possível verificar modelos em memória: {e}")

print(f"\n{'='*50}")
print("RESUMO")
print(f"{'='*50}")
if t1 and t2:
    ganho = ((t1 - t2) / t1) * 100
    print(f"  Original:   {t1:.1f}s")
    print(f"  Otimizado:  {t2:.1f}s")
    print(f"  Melhoria:   {ganho:.0f}% mais rápido")
if t3:
    print(f"  Baseline:   {t3:.1f}s (modelo puro sem system prompt)")
    print()
    if t3 and t2 and t2 > t3 * 5:
        print("  ATENÇÃO: O modelo está muito mais lento que o baseline.")
        print("  Possíveis causas:")
        print("    1. Modelo rodando em CPU (sem GPU) — lentidão esperada")
        print("    2. RAM insuficiente — modelo sofre swap para disco")
        print("    3. Modelo não estava carregado na memória (cold start)")
        print()
        print("  Soluções:")
        print("    - Verifique se tem GPU disponível: nvidia-smi ou rocm-smi")
        print("    - Use um modelo menor: ollama pull qwen2.5:1.5b")
        print("    - Mantenha o Ollama sempre rodando: ollama serve")