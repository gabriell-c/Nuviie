"""
diagnostico_scraper.py
======================
Execute na raiz do projeto com o venv ativado:

    python diagnostico_scraper.py

Diagnóstica todos os pontos de falha conhecidos do scraper Google Maps
quando chamado via Django (subprocess) no Windows/Linux.
"""

import sys
import os
import subprocess
import json
import base64
import pathlib
import time

SEP = "─" * 60

def ok(msg):  print(f"  ✅  {msg}")
def warn(msg): print(f"  ⚠️   {msg}")
def err(msg):  print(f"  ❌  {msg}")
def info(msg): print(f"  ℹ️   {msg}")


print(SEP)
print("DIAGNÓSTICO DO SCRAPER GOOGLE MAPS — Nuviie")
print(SEP)

# ─────────────────────────────────────────────────────────────────────────────
print("\n[1] Python & ambiente")
ok(f"Python: {sys.version.split()[0]}")
ok(f"Executable: {sys.executable}")
info(f"Platform: {sys.platform}")
info(f"CWD: {os.getcwd()}")

# ─────────────────────────────────────────────────────────────────────────────
print("\n[2] Playwright instalado?")
try:
    import playwright
    v = getattr(playwright, '__version__', 'desconhecida')
    ok(f"playwright=={v}")
except ImportError:
    err("Playwright NÃO instalado!")
    err("Execute: pip install playwright && playwright install chromium")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
print("\n[3] Chromium do Playwright instalado?")
home = pathlib.Path.home()
username = os.environ.get('USERNAME') or os.environ.get('USER') or ''
candidates = [
    home / 'AppData' / 'Local' / 'ms-playwright',
    home / '.cache' / 'ms-playwright',
    pathlib.Path('/root/.cache/ms-playwright'),
]
if username:
    candidates.append(pathlib.Path(f'/home/{username}/.cache/ms-playwright'))

pw_dir = None
chromium_dir = None
for c in candidates:
    if c.exists():
        pw_dir = c
        chromium_dirs = list(c.glob('chromium-*'))
        if chromium_dirs:
            chromium_dir = chromium_dirs[0]
            break

if chromium_dir:
    ok(f"Chromium encontrado: {chromium_dir}")
    # Verifica executável
    if sys.platform == 'win32':
        chrome_exe = chromium_dir / 'chrome-win' / 'chrome.exe'
    else:
        chrome_exe = chromium_dir / 'chrome-linux' / 'chrome'
    if chrome_exe.exists():
        ok(f"Executável existe: {chrome_exe}")
    else:
        warn(f"Executável NÃO encontrado em: {chrome_exe}")
        warn("Tente: playwright install chromium")
elif pw_dir:
    err(f"Diretório ms-playwright existe ({pw_dir}) mas sem chromium!")
    err("Execute: playwright install chromium")
else:
    err("ms-playwright NÃO encontrado em nenhum caminho padrão!")
    err("Execute: playwright install chromium")

# ─────────────────────────────────────────────────────────────────────────────
print("\n[4] PLAYWRIGHT_BROWSERS_PATH definido?")
pw_browsers_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
if pw_browsers_path:
    ok(f"PLAYWRIGHT_BROWSERS_PATH={pw_browsers_path}")
else:
    if chromium_dir:
        warn("PLAYWRIGHT_BROWSERS_PATH não definido, mas Chromium foi encontrado automaticamente.")
        info(f"Opcional: defina no .env → PLAYWRIGHT_BROWSERS_PATH={pw_dir}")
    else:
        err("PLAYWRIGHT_BROWSERS_PATH não definido E Chromium não encontrado!")

# ─────────────────────────────────────────────────────────────────────────────
print("\n[5] scraper_runner.py acessível?")
runner_candidates = [
    pathlib.Path('leads') / 'scraper_runner.py',
    pathlib.Path('scraper_runner.py'),
]
runner_found = None
for r in runner_candidates:
    if r.exists():
        runner_found = r.resolve()
        ok(f"Encontrado: {runner_found}")
        break
if not runner_found:
    err("scraper_runner.py NÃO encontrado!")
    err("Esperado em: leads/scraper_runner.py")

# ─────────────────────────────────────────────────────────────────────────────
print("\n[6] scraper.py acessível?")
scraper_candidates = [
    pathlib.Path('leads') / 'scraper.py',
    pathlib.Path('scraper.py'),
]
scraper_found = None
for s in scraper_candidates:
    if s.exists():
        scraper_found = s.resolve()
        ok(f"Encontrado: {scraper_found}")
        break
if not scraper_found:
    warn("scraper.py não encontrado nos caminhos testados")

# ─────────────────────────────────────────────────────────────────────────────
print("\n[7] Django setup (simulando o subprocess)")
django_settings = os.environ.get('DJANGO_SETTINGS_MODULE', 'core.settings')
info(f"DJANGO_SETTINGS_MODULE={django_settings}")
try:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', django_settings)
    import django
    django.setup()
    ok("Django setup: OK")
except Exception as e:
    err(f"Django setup FALHOU: {e}")
    warn("O subprocess também vai falhar no Django setup.")
    warn("Verifique seu DJANGO_SETTINGS_MODULE e PYTHONPATH.")

# ─────────────────────────────────────────────────────────────────────────────
print("\n[8] Import de _scrape_google_maps_async")
try:
    from leads.scraper import _scrape_google_maps_async
    ok("Import OK: leads.scraper._scrape_google_maps_async")
except Exception as e:
    err(f"Import FALHOU: {e}")
    warn("O subprocesso não conseguirá importar a função de scraping.")

# ─────────────────────────────────────────────────────────────────────────────
print("\n[9] Teste rápido do Playwright (abre Chromium e fecha)")
try:
    import asyncio
    from playwright.async_api import async_playwright

    async def _test_playwright():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
            page = await browser.new_page()
            await page.goto('https://www.google.com', timeout=15000)
            title = await page.title()
            await browser.close()
            return title

    start = time.time()
    title = asyncio.run(_test_playwright())
    elapsed = time.time() - start
    ok(f"Playwright OK ({elapsed:.1f}s) — título: {title!r}")
except Exception as e:
    err(f"Playwright FALHOU: {e}")
    err("Este é provavelmente o motivo do erro no CRM!")
    import traceback
    traceback.print_exc()

# ─────────────────────────────────────────────────────────────────────────────
if runner_found:
    print("\n[10] Teste do subprocesso scraper_runner.py (simulação real)")
    test_args = {
        '_settings_module': os.environ.get('DJANGO_SETTINGS_MODULE', 'core.settings'),
        'niche': 'restaurante',
        'city': 'São Paulo',
        'limit': 2,
        'only_without_website': False,
        'min_rating': None,
        'min_reviews': None,
        'only_with_instagram': False,
        'only_with_facebook': False,
    }
    args_b64 = base64.b64encode(json.dumps(test_args).encode()).decode()
    subprocess_env = os.environ.copy()
    subprocess_env['PYTHONIOENCODING'] = 'utf-8'
    subprocess_env['PYTHONUNBUFFERED'] = '1'
    if pw_dir and not subprocess_env.get('PLAYWRIGHT_BROWSERS_PATH'):
        subprocess_env['PLAYWRIGHT_BROWSERS_PATH'] = str(pw_dir)

    info("Rodando subprocesso (timeout=120s, limit=2 para teste rápido)...")
    info(f"cmd: {sys.executable} {runner_found} <args_b64>")

    try:
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, str(runner_found), args_b64],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=120,
            cwd=str(runner_found.parent),
            env=subprocess_env,
        )
        elapsed = time.time() - t0
        info(f"Subprocesso terminou em {elapsed:.1f}s, exit code={proc.returncode}")

        if proc.stderr.strip():
            print("\n  --- STDERR do subprocesso ---")
            for line in proc.stderr.splitlines()[-40:]:
                print(f"  | {line}")

        result_line = None
        for line in proc.stdout.splitlines():
            if line.startswith('__SCRAPER_RESULT__'):
                result_line = line[len('__SCRAPER_RESULT__'):]
                break

        if result_line:
            results = json.loads(result_line)
            if results:
                ok(f"Subprocesso retornou {len(results)} lead(s)! ✨")
                for r in results:
                    info(f"  → {r.get('name')} | {r.get('phone_number')} | {r.get('instagram')}")
            else:
                warn("Subprocesso rodou mas retornou 0 leads.")
                warn("Pode ser bloqueio do Google Maps ou seletor desatualizado.")
        else:
            err("Marcador __SCRAPER_RESULT__ não encontrado no stdout!")
            print("\n  --- STDOUT completo ---")
            for line in proc.stdout.splitlines()[-20:]:
                print(f"  | {line}")

    except subprocess.TimeoutExpired:
        err("Timeout de 120s expirado!")
        err("O subprocesso está travando. Verifique o log acima.")
    except Exception as e:
        err(f"Erro ao executar subprocesso: {e}")
        import traceback
        traceback.print_exc()
else:
    warn("\n[10] Pulando teste do subprocesso (runner não encontrado)")

# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("DIAGNÓSTICO CONCLUÍDO")
print(SEP)
print()
print("Se o teste [9] passou mas o [10] falhou:")
print("  → O problema está no subprocess Django (env, cwd, import path)")
print("  → Substitua leads/scraper_runner.py pelo arquivo v6 fornecido")
print("  → Substitua a função scrape_google_maps() em scraper.py pelo patch v6")
print()
print("Se o teste [9] falhou:")
print("  → O Playwright ou Chromium não está funcionando neste Python/venv")
print("  → Execute: pip install playwright && playwright install chromium")
print()
print("Se tudo passou mas o CRM ainda falha:")
print("  → Verifique se o Django está usando o mesmo Python/venv")
print("  → Adicione MAPS_SCRAPER_TIMEOUT=360 no seu .env")
print("  → Verifique se há firewall/proxy bloqueando o Chromium")
