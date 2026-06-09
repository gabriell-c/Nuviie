"""
preview_runner.py — Nuviie Browser Preview
===========================================
Subprocesso isolado: recebe uma URL via base64, abre com Playwright/Firefox,
tira um screenshot de página inteira e retorna como base64 no stdout.

Protocolo (igual ao scraper_runner):
  Entrada : sys.argv[1] = base64(json({'url': '...', 'viewport_width': 1280}))
  Saída   : print("__PREVIEW_RESULT__<base64_da_imagem_png>")
  Erro    : print("__PREVIEW_ERROR__<mensagem>")

Uso (pelo Django via subprocess):
  python preview_runner.py <base64_args>
"""

import sys
import os

# ── Força UTF-8 ────────────────────────────────────────────────────────────────
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

import json
import base64
import asyncio
import traceback
import logging
import time

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('preview_runner')


def _find_playwright_browsers_path():
    import pathlib
    home = pathlib.Path.home()
    candidates = [
        home / 'AppData' / 'Local' / 'ms-playwright',
        home / '.cache' / 'ms-playwright',
        pathlib.Path('/root/.cache/ms-playwright'),
    ]
    username = os.environ.get('USER', '')
    if username:
        candidates.append(pathlib.Path(f'/home/{username}/.cache/ms-playwright'))
    for c in candidates:
        if c.exists() and list(c.glob('firefox-*')):
            return str(c)
    return None


def _setup_playwright_env():
    if not os.environ.get('PLAYWRIGHT_BROWSERS_PATH'):
        found = _find_playwright_browsers_path()
        if found:
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = found


async def _take_screenshot(url: str, viewport_width: int = 1280, timeout_ms: int = 25000) -> bytes:
    """
    Abre a URL com Firefox headless e retorna o screenshot como bytes PNG.
    """
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout

    async with async_playwright() as p:
        browser = await p.firefox.launch(
            headless=True,
            firefox_user_prefs={
                'intl.accept_languages': 'pt-BR, pt, en-US, en',
                'dom.webdriver.enabled': False,
                'privacy.resistFingerprinting': False,
                'geo.enabled': False,
            }
        )

        context = await browser.new_context(
            locale='pt-BR',
            timezone_id='America/Sao_Paulo',
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) '
                'Gecko/20100101 Firefox/125.0'
            ),
            viewport={'width': viewport_width, 'height': 900},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        page = await context.new_page()

        # Bloqueia fontes/vídeos para ser mais rápido; mantém imagens (são importantes no Maps)
        await page.route(
            '**/*.{woff,woff2,ttf,otf,mp4,mp3}',
            lambda r: r.abort()
        )

        logger.info(f"[Preview] Navegando para: {url}")
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=timeout_ms)
        except PWTimeout:
            logger.warning("[Preview] timeout no goto — tirando screenshot do que carregou")
        except Exception as e:
            logger.warning(f"[Preview] Erro no goto: {e} — tentando screenshot assim mesmo")

        # Aguarda conteúdo principal aparecer
        await asyncio.sleep(3)

        # Tenta aceitar consentimento se aparecer
        for sel in [
            'button:has-text("Aceitar tudo")',
            'button:has-text("Accept all")',
            '#L2AGLb',
            'button:has-text("Concordar")',
        ]:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(1.5)
                    logger.info(f"[Preview] Consentimento aceito via: {sel}")
                    break
            except Exception:
                pass

        # Scroll para carregar lazy content
        try:
            await page.evaluate("window.scrollTo(0, 400)")
            await asyncio.sleep(1)
        except Exception:
            pass

        logger.info("[Preview] Tirando screenshot...")
        screenshot_bytes = await page.screenshot(full_page=False, type='png')
        logger.info(f"[Preview] Screenshot OK — {len(screenshot_bytes)} bytes")

        await context.close()
        await browser.close()

        return screenshot_bytes


def main():
    if len(sys.argv) < 2:
        print("__PREVIEW_ERROR__Uso: preview_runner.py <base64_args>", flush=True)
        sys.exit(1)

    # Decodifica args
    try:
        raw = base64.b64decode(sys.argv[1]).decode('utf-8')
        args = json.loads(raw)
        url = args.get('url', '').strip()
        viewport_width = int(args.get('viewport_width', 1280))
        timeout_ms = int(args.get('timeout_ms', 25000))
    except Exception as e:
        print(f"__PREVIEW_ERROR__Falha ao decodificar args: {e}", flush=True)
        sys.exit(1)

    if not url:
        print("__PREVIEW_ERROR__URL não fornecida", flush=True)
        sys.exit(1)

    # Valida que a URL é http/https para evitar uso indevido
    if not url.startswith(('http://', 'https://')):
        print("__PREVIEW_ERROR__URL inválida — apenas http/https", flush=True)
        sys.exit(1)

    logger.info(f"[Preview] Iniciando preview para: {url}")

    # Setup Playwright
    _setup_playwright_env()

    # Executa
    try:
        screenshot_bytes = asyncio.run(_take_screenshot(url, viewport_width, timeout_ms))
        img_b64 = base64.b64encode(screenshot_bytes).decode('ascii')
        print(f"__PREVIEW_RESULT__{img_b64}", flush=True)
        logger.info("[Preview] Resultado enviado com sucesso.")
    except Exception as e:
        logger.error(f"[Preview] Erro ao tirar screenshot: {e}")
        logger.error(traceback.format_exc())
        print(f"__PREVIEW_ERROR__{e}", flush=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
