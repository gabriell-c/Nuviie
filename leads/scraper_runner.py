"""
scraper_runner.py — v7 (Nuviie)
================================
Subprocesso isolado chamado pelo Django para executar o Playwright
sem conflitos de event loop no Windows/Linux.

ROLLBACK STAGES (procure nos logs do Django via [Maps:worker]):
  [R-STEP 1] Setup de encoding e sys.path
  [R-STEP 2] Decodificação dos args base64
  [R-STEP 3] Verificação de ambiente (Python, Playwright, Firefox)
  [R-STEP 4] Setup Django
  [R-STEP 5] Import do scraper
  [R-STEP 6] Execução async do scraper
  [R-STEP 7] Serialização e envio do resultado

Salve este arquivo em: leads/scraper_runner.py
"""

import sys
import os

# ── [R-STEP 1] Força UTF-8 e setup de encoding ───────────────────────────────
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

import json
import base64
import asyncio
import traceback
import threading
import time
import logging


# ── Logging direto no stderr ──────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stderr,
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('runner')


def step(n: int, msg: str, level: str = 'info'):
    """Log de rollback com número de etapa."""
    fn = getattr(logger, level, logger.info)
    fn(f"[R-STEP {n}] {msg}")


def diag(msg: str, level: str = 'info'):
    fn = getattr(logger, level, logger.info)
    fn(f"[runner] {msg}")


# ── Heartbeat: loga a cada 30s para mostrar que o processo está vivo ─────────
_heartbeat_running = True

def _heartbeat():
    start = time.time()
    while _heartbeat_running:
        time.sleep(30)
        if _heartbeat_running:
            elapsed = int(time.time() - start)
            diag(f"heartbeat — {elapsed}s decorridos, processo ativo...")

threading.Thread(target=_heartbeat, daemon=True).start()


# ── Utilitário: encontra diretório do ms-playwright ──────────────────────────
def _find_playwright_browsers_path():
    import pathlib
    home = pathlib.Path.home()
    username = os.environ.get('USERNAME') or os.environ.get('USER') or ''

    candidates = [
        home / 'AppData' / 'Local' / 'ms-playwright',
        home / '.cache' / 'ms-playwright',
        pathlib.Path('/root/.cache/ms-playwright'),
    ]
    if username:
        candidates.append(pathlib.Path(f'/home/{username}/.cache/ms-playwright'))

    for c in candidates:
        if c.exists() and list(c.glob('firefox-*')):
            diag(f"Playwright browsers encontrado: {c}")
            return str(c)

    diag("AVISO: ms-playwright nao encontrado nos caminhos padrao!", 'warning')
    return None


def _setup_playwright_env():
    if os.environ.get('PLAYWRIGHT_BROWSERS_PATH'):
        diag(f"PLAYWRIGHT_BROWSERS_PATH já definido: {os.environ['PLAYWRIGHT_BROWSERS_PATH']}")
        return
    found = _find_playwright_browsers_path()
    if found:
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = found
        diag(f"PLAYWRIGHT_BROWSERS_PATH definido: {found}")
    else:
        diag("PLAYWRIGHT_BROWSERS_PATH nao definido — Playwright pode falhar!", 'warning')


def _check_env(step_n: int):
    """Verificação completa do ambiente com logs de rollback."""
    step(step_n, f"Python    : {sys.version.split()[0]} — {sys.executable}")
    step(step_n, f"Platform  : {sys.platform}")
    step(step_n, f"CWD       : {os.getcwd()}")
    step(step_n, f"PID       : {os.getpid()}")
    step(step_n, f"DJANGO    : {os.environ.get('DJANGO_SETTINGS_MODULE', '<nao definido>')}")
    step(step_n, f"PW_PATH   : {os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '<nao definido>')}")

    # Verifica Playwright
    try:
        import playwright
        version = getattr(playwright, '__version__', 'ok')
        step(step_n, f"✓ Playwright instalado — versão: {version}")
    except ImportError:
        step(step_n, "✗ PLAYWRIGHT NAO INSTALADO! Execute: pip install playwright && playwright install firefox", 'error')
        return False

    # Verifica Firefox
    import pathlib
    home = pathlib.Path.home()
    username = os.environ.get('USER', '')
    pw_env = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '')
    candidates = [
        pathlib.Path(pw_env) if pw_env else None,
        home / '.cache' / 'ms-playwright',
        home / 'AppData' / 'Local' / 'ms-playwright',
        pathlib.Path('/root/.cache/ms-playwright'),
    ]
    if username:
        candidates.append(pathlib.Path(f'/home/{username}/.cache/ms-playwright'))

    firefox_found = False
    for c in candidates:
        if c and c.exists():
            firefox_dirs = list(c.glob('firefox-*'))
            if firefox_dirs:
                step(step_n, f"✓ Firefox encontrado: {c}/{firefox_dirs[0].name}")
                firefox_found = True
                break
            else:
                step(step_n, f"  Diretório ms-playwright existe mas sem firefox-*: {c}", 'warning')

    if not firefox_found:
        step(step_n, "✗ FIREFOX NAO ENCONTRADO! Execute: playwright install firefox", 'error')
        return False

    _setup_playwright_env()
    return True


# ── [R-STEP 4] Setup Django ───────────────────────────────────────────────────
def _setup_django(project_root: str, settings_module: str) -> bool:
    step(4, f"project_root    : {project_root}")
    step(4, f"settings_module : {settings_module}")

    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        step(4, f"✓ project_root adicionado ao sys.path")
    else:
        step(4, f"  project_root já estava no sys.path")

    os.environ['DJANGO_SETTINGS_MODULE'] = settings_module

    try:
        import django
        django.setup()
        step(4, "✓ Django setup: OK")
        # Force-reconfigure all loggers to output to stderr
        # Django's LOGGING config in settings.py can suppress 'leads.scraper' logger.
        # We override this here so _pw_diag() still works, but also ensure
        # the standard logger calls in scraper.py are visible.
        try:
            import logging as _logging
            _handler = _logging.StreamHandler(sys.stderr)
            _handler.setLevel(_logging.DEBUG)
            _handler.setFormatter(_logging.Formatter(
                '%(asctime)s %(levelname)s %(name)s: %(message)s', '%H:%M:%S'
            ))
            for _name in ('leads.scraper', 'scraper_direct', 'scraper', ''):
                _lg = _logging.getLogger(_name)
                _lg.setLevel(_logging.DEBUG)
                # Avoid duplicate handlers
                if not any(isinstance(h, _logging.StreamHandler) and h.stream is sys.stderr
                           for h in _lg.handlers):
                    _lg.addHandler(_handler)
                _lg.propagate = True
            step(4, "✓ Logger reconfigured para stderr após django.setup()")
        except Exception as _le:
            step(4, f"Aviso: falha ao reconfigurar logger: {_le}", 'warning')
        return True
    except Exception as e:
        step(4, f"✗ Django setup FALHOU: {e}", 'error')
        step(4, traceback.format_exc(), 'error')
        step(4, "  → O scraper tentará importar sem Django (modo standalone)", 'warning')
        return False


# ── [R-STEP 5] Import do scraper ──────────────────────────────────────────────
def _import_scraper():
    step(5, "Tentando import via 'leads.scraper'...")
    try:
        from leads.scraper import _scrape_google_maps_async
        step(5, "✓ Import via 'leads.scraper': OK")
        return _scrape_google_maps_async
    except ImportError as e:
        step(5, f"  Import via 'leads.scraper' falhou (ImportError): {e}", 'warning')
    except Exception as e:
        step(5, f"  Import via 'leads.scraper' falhou ({type(e).__name__}): {e}", 'warning')

    # Fallback: importa direto pelo caminho do arquivo
    step(5, "Tentando import via caminho direto do arquivo...")
    try:
        import importlib.util
        runner_dir = os.path.dirname(os.path.abspath(__file__))
        scraper_path = os.path.join(runner_dir, 'scraper.py')
        step(5, f"  scraper_path : {scraper_path}")
        if os.path.exists(scraper_path):
            spec = importlib.util.spec_from_file_location('scraper_direct', scraper_path)
            mod = importlib.util.module_from_spec(spec)
            # Adiciona ao sys.modules para evitar import duplo
            sys.modules['scraper_direct'] = mod
            spec.loader.exec_module(mod)
            fn = getattr(mod, '_scrape_google_maps_async', None)
            if fn:
                step(5, "✓ Import via caminho direto: OK")
                return fn
            else:
                step(5, "✗ _scrape_google_maps_async não encontrada no módulo!", 'error')
        else:
            step(5, f"✗ scraper.py não encontrado em: {scraper_path}", 'error')
    except Exception as e:
        step(5, f"✗ Import direto também falhou: {e}", 'error')
        step(5, traceback.format_exc(), 'error')

    return None


# ── Execução principal ────────────────────────────────────────────────────────
def main():
    global _heartbeat_running

    step(1, "══ scraper_runner.py v7 iniciado ══")
    step(1, f"Python: {sys.version.split()[0]} | PID: {os.getpid()} | Platform: {sys.platform}")

    if len(sys.argv) < 2:
        print("USO: scraper_runner.py <base64_args>", file=sys.stderr)
        print("__SCRAPER_RESULT__[]", flush=True)
        sys.exit(1)

    # ── [R-STEP 2] Decodificação dos args ─────────────────────────────────────
    step(2, "Decodificando args base64...")
    try:
        raw = base64.b64decode(sys.argv[1]).decode('utf-8')
        args = json.loads(raw)
        step(2, f"✓ Args decodificados: niche={args.get('niche')!r} city={args.get('city')!r} limit={args.get('limit')}")
        step(2, f"  Filtros: sem_site={args.get('only_without_website')} min_rating={args.get('min_rating')} min_reviews={args.get('min_reviews')}")
        step(2, f"  Filtros: ig={args.get('only_with_instagram')} fb={args.get('only_with_facebook')}")
    except Exception as e:
        step(2, f"✗ FALHOU ao decodificar args: {e}", 'error')
        print("__SCRAPER_RESULT__[]", flush=True)
        _heartbeat_running = False
        sys.exit(1)

    # Extrai metadados antes de passar para o scraper
    settings_module = args.pop('_settings_module', 'core.settings')

    # project_root = dois níveis acima deste arquivo
    runner_file  = os.path.abspath(__file__)
    leads_dir    = os.path.dirname(runner_file)
    project_root = os.path.dirname(leads_dir)

    step(2, f"runner_file  : {runner_file}")
    step(2, f"leads_dir    : {leads_dir}")
    step(2, f"project_root : {project_root}")

    # Adiciona caminhos ao sys.path
    for p in [project_root, leads_dir]:
        if p not in sys.path:
            sys.path.insert(0, p)
            step(2, f"  → Adicionado ao sys.path: {p}")

    # ── [R-STEP 3] Verificação de ambiente ────────────────────────────────────
    step(3, "══ Verificando ambiente Playwright ══")
    env_ok = _check_env(3)
    if not env_ok:
        step(3, "✗ Ambiente INVÁLIDO — abortando. Veja logs [R-STEP 3] acima.", 'error')
        print("__SCRAPER_RESULT__[]", flush=True)
        _heartbeat_running = False
        sys.exit(1)
    step(3, "✓ Ambiente OK")

    # ── [R-STEP 4] Setup Django ───────────────────────────────────────────────
    step(4, "══ Setup Django ══")
    django_ok = _setup_django(project_root, settings_module)
    if not django_ok:
        step(4, "⚠️  Django não carregou — tentando importar scraper diretamente...", 'warning')

    # ── [R-STEP 5] Import do scraper ──────────────────────────────────────────
    step(5, "══ Importando _scrape_google_maps_async ══")
    scrape_fn = _import_scraper()
    if scrape_fn is None:
        step(5, "✗ FALHA FATAL: não foi possível importar _scrape_google_maps_async", 'error')
        step(5, "  → Verifique se scraper.py está na mesma pasta de scraper_runner.py", 'error')
        print("__SCRAPER_RESULT__[]", flush=True)
        _heartbeat_running = False
        sys.exit(1)
    step(5, f"✓ Função importada: {scrape_fn}")

    # ── [R-STEP 6] Execução async ─────────────────────────────────────────────
    timeout_s = int(os.environ.get('MAPS_SCRAPER_TIMEOUT', 300))
    step(6, f"══ Executando asyncio.run() | timeout={timeout_s}s ══")
    step(6, f"  Args para o scraper: {list(args.keys())}")

    async def run():
        return await asyncio.wait_for(
            scrape_fn(**args),
            timeout=timeout_s - 10
        )

    try:
        results = asyncio.run(run())
        step(6, f"✓ asyncio.run() concluído: {len(results)} resultados")
        if len(results) == 0:
            step(6, "⚠️  ZERO resultados — veja logs do Playwright acima (feed, CAPTCHA, etc.)", 'warning')
        else:
            for i, r in enumerate(results[:3]):
                step(6, f"  Resultado {i+1}: {r.get('name')} | {r.get('city')} | tel={r.get('phone_number')}")
    except asyncio.TimeoutError:
        step(6, f"✗ TIMEOUT: scraper excedeu {timeout_s}s", 'error')
        step(6, f"  → Aumente MAPS_SCRAPER_TIMEOUT no .env ou reduza o limite", 'error')
        print("__SCRAPER_RESULT__[]", flush=True)
        _heartbeat_running = False
        sys.exit(1)
    except Exception as e:
        step(6, f"✗ ERRO em asyncio.run(): {e}", 'error')
        step(6, traceback.format_exc(), 'error')
        print("__SCRAPER_RESULT__[]", flush=True)
        _heartbeat_running = False
        sys.exit(1)

    # ── [R-STEP 7] Serialização e envio ──────────────────────────────────────
    step(7, "══ Serializando e enviando resultado ══")
    try:
        output = json.dumps(results, ensure_ascii=False)
        step(7, f"✓ JSON serializado ({len(output)} chars) — enviando ao processo pai")
        print(f"__SCRAPER_RESULT__{output}", flush=True)
        step(7, "✓ Resultado enviado. Encerrando com sucesso.")
    except Exception as e:
        step(7, f"✗ Erro ao serializar resultado: {e}", 'error')
        print("__SCRAPER_RESULT__[]", flush=True)
        _heartbeat_running = False
        sys.exit(1)

    _heartbeat_running = False


if __name__ == '__main__':
    main()