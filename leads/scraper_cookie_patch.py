"""
scraper_cookie_patch.py — Instruções de patch para scraper.py
==============================================================
Aplique as 3 alterações abaixo no seu scraper.py existente.
Cada bloco mostra EXATAMENTE o trecho a substituir.

Você pode aplicar manualmente ou rodar:
    python scraper_cookie_patch.py

O script aplica o patch automaticamente se encontrar o scraper.py
na mesma pasta.
"""

# ══════════════════════════════════════════════════════════════════════════════
# ALTERAÇÃO 1 — Adicionar import do cookie_manager
# Onde: logo após "import os" e "import sys" no topo de scraper.py
# ══════════════════════════════════════════════════════════════════════════════

PATCH_1_OLD = '''\
logger = logging.getLogger(__name__)'''

PATCH_1_NEW = '''\
logger = logging.getLogger(__name__)

# ── Cookie Manager: injeta sessão real do Google no Playwright ─────────────
try:
    from .cookie_manager import inject_google_cookies, check_cookies_freshness
    _COOKIE_MANAGER_OK = True
except ImportError:
    try:
        from cookie_manager import inject_google_cookies, check_cookies_freshness
        _COOKIE_MANAGER_OK = True
    except ImportError:
        _COOKIE_MANAGER_OK = False
        def inject_google_cookies(ctx): return False
        def check_cookies_freshness(): return {}
        logger.warning("[Maps] cookie_manager não encontrado — scraper rodará sem cookies injetados")'''


# ══════════════════════════════════════════════════════════════════════════════
# ALTERAÇÃO 2 — Injetar cookies logo após criar o contexto Playwright
# Onde: dentro de _scrape_google_maps_async, após "context = await _new_context_async(...)"
# ══════════════════════════════════════════════════════════════════════════════

PATCH_2_OLD = '''\
        context = await _new_context_async(browser, **context_kwargs)

        search_page = await context.new_page()'''

PATCH_2_NEW = '''\
        context = await _new_context_async(browser, **context_kwargs)

        # ── Injeta cookies reais do Google ────────────────────────────────────
        # Isso faz o Google Maps tratar o Playwright como um usuário humano
        # logado, entregando dados completos (horários, avaliações, telefone).
        if _COOKIE_MANAGER_OK:
            cookies_ok = await inject_google_cookies(context)
            if cookies_ok:
                _pw_diag("[Maps][COOKIES] ✓ Cookies do Google injetados com sucesso")
            else:
                _pw_diag(
                    "[Maps][COOKIES] ⚠️  Cookies NÃO injetados. "
                    "Exporte seus cookies do Maps e salve em leads/google_cookies.json",
                    "warning"
                )
        else:
            _pw_diag("[Maps][COOKIES] ⚠️  cookie_manager indisponível", "warning")

        search_page = await context.new_page()'''


# ══════════════════════════════════════════════════════════════════════════════
# ALTERAÇÃO 3 — Logar status dos cookies no início do run_google_maps_scraper
# Onde: dentro de run_google_maps_scraper(), logo após o logger.info inicial
# ══════════════════════════════════════════════════════════════════════════════

PATCH_3_OLD = '''\
    logger.info(f"[Maps][PIPELINE A] ══ Iniciando scraper Google Maps ══")'''

PATCH_3_NEW = '''\
    logger.info(f"[Maps][PIPELINE A] ══ Iniciando scraper Google Maps ══")

    # Verifica saúde dos cookies antes de cada execução
    if _COOKIE_MANAGER_OK:
        cookie_status = check_cookies_freshness()
        if cookie_status.get('estimated_valid'):
            logger.info(
                f"[Maps][COOKIES] ✓ Cookies OK | "
                f"Essenciais: {', '.join(cookie_status.get('essential_present', []))} | "
                f"Idade: {cookie_status.get('age_days')} dias"
            )
        else:
            for w in cookie_status.get('warnings', []):
                logger.warning(f"[Maps][COOKIES] ⚠️  {w}")
            if not cookie_status.get('file_found'):
                logger.warning(
                    "[Maps][COOKIES] 📋 Para extrair dados completos, exporte seus cookies:\n"
                    "  1. Instale 'Cookie-Editor' no Firefox\n"
                    "  2. Acesse maps.google.com.br logado\n"
                    "  3. Export → Export as JSON → salve em leads/google_cookies.json"
                )'''


# ══════════════════════════════════════════════════════════════════════════════
# Script de aplicação automática
# ══════════════════════════════════════════════════════════════════════════════

def apply_patch():
    import pathlib, sys

    scraper_path = pathlib.Path(__file__).parent / 'scraper.py'
    if not scraper_path.exists():
        print(f"❌  scraper.py não encontrado em: {scraper_path}")
        print("   Coloque este arquivo na mesma pasta do scraper.py e tente novamente.")
        sys.exit(1)

    content = scraper_path.read_text(encoding='utf-8')
    original = content

    patches = [
        ('Patch 1 — import cookie_manager', PATCH_1_OLD, PATCH_1_NEW),
        ('Patch 2 — inject cookies após new_context', PATCH_2_OLD, PATCH_2_NEW),
        ('Patch 3 — log status no pipeline', PATCH_3_OLD, PATCH_3_NEW),
    ]

    applied = []
    skipped = []
    errors  = []

    for name, old, new in patches:
        if old not in content:
            if new in content:
                skipped.append(f"  ⏭  {name} — já aplicado, pulando")
            else:
                errors.append(f"  ❌  {name} — trecho original não encontrado no scraper.py")
            continue

        count = content.count(old)
        if count > 1:
            errors.append(f"  ❌  {name} — trecho encontrado {count}x (ambíguo), aplique manualmente")
            continue

        content = content.replace(old, new, 1)
        applied.append(f"  ✅  {name}")

    print("\n" + "═" * 55)
    print("  Nuviie — Aplicando patch de cookies no scraper.py")
    print("═" * 55)

    if errors:
        print("\n  ERROS (patch não aplicado para estes itens):")
        for e in errors:
            print(e)

    if skipped:
        print("\n  JÁ APLICADOS:")
        for s in skipped:
            print(s)

    if applied:
        # Backup antes de sobrescrever
        backup = scraper_path.with_suffix('.py.bak')
        backup.write_text(original, encoding='utf-8')
        print(f"\n  Backup salvo em: {backup.name}")

        scraper_path.write_text(content, encoding='utf-8')
        print("\n  APLICADOS COM SUCESSO:")
        for a in applied:
            print(a)
    else:
        print("\n  Nenhuma alteração necessária.")

    if errors:
        print("\n  ⚠️  Alguns patches falharam — veja ERROS acima.")
        print("     Aplique manualmente consultando este arquivo.")
        sys.exit(1)

    print("\n  Próximo passo:")
    print("  → Exporte seus cookies do Google Maps e salve em leads/google_cookies.json")
    print("  → Instruções detalhadas: python -c \"from leads.cookie_manager import print_cookie_status; print_cookie_status()\"")
    print("═" * 55 + "\n")


if __name__ == '__main__':
    apply_patch()
