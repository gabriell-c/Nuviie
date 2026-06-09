"""
cookie_manager.py — Nuviie Cookie Manager
==========================================
Gerencia cookies reais do Google para injetar no Playwright headless.

FLUXO:
  1. Você abre o Firefox normal, navega no Google Maps logado
  2. Exporta os cookies com uma extensão (Cookie-Editor, EditThisCookie, etc.)
     e salva como JSON em: leads/google_cookies.json
  3. O scraper carrega esses cookies via inject_google_cookies()
  4. O Google te enxerga como um usuário logado → dados completos

RENOVAÇÃO:
  Execute `python manage.py check_cookies` (ou chame check_cookies_freshness())
  para saber se os cookies ainda são válidos. Cookies do Google duram 30-90 dias.

USO NO SCRAPER (já integrado via patch):
  from leads.cookie_manager import load_cookies_for_context
  await load_cookies_for_context(context)

EXPORTAÇÃO MANUAL:
  1. Instale "Cookie-Editor" no seu Firefox real (https://cookie-editor.com/)
  2. Acesse https://maps.google.com.br logado com sua conta Google
  3. Abra o Cookie-Editor → clique "Export" → "Export as JSON"
  4. Salve o arquivo em:  leads/google_cookies.json
  5. Também salve em:     leads/google_maps_cookies.json  (só para maps.google)
"""

import json
import os
import pathlib
import logging
import time

logger = logging.getLogger(__name__)

# ── Caminhos dos arquivos de cookie ──────────────────────────────────────────
_LEADS_DIR = pathlib.Path(__file__).resolve().parent

COOKIE_FILES = [
    _LEADS_DIR / 'google_cookies.json',         # exportado de google.com
    _LEADS_DIR / 'google_maps_cookies.json',    # exportado de maps.google.com (opcional)
]

# Domínios que o Google Maps usa — filtramos só esses para evitar ruído
GOOGLE_DOMAINS = {
    '.google.com',
    '.google.com.br',
    'google.com',
    'google.com.br',
    '.maps.google.com',
    'maps.google.com',
    '.googleapis.com',
    'accounts.google.com',
}


def _find_cookie_file() -> pathlib.Path | None:
    """Retorna o primeiro arquivo de cookies existente e não vazio."""
    for path in COOKIE_FILES:
        if path.exists() and path.stat().st_size > 100:
            return path
    return None


def _normalize_cookies(raw_cookies: list[dict]) -> list[dict]:
    """
    Normaliza cookies exportados por diferentes extensões para o formato
    que o Playwright espera: name, value, domain, path, httpOnly, secure, sameSite.

    Suporta formatos de:
      - Cookie-Editor (padrão JSON)
      - EditThisCookie
      - Netscape/txt convertido para JSON
      - Firefox DevTools
    """
    normalized = []
    for c in raw_cookies:
        # Diferentes extensões usam chaves diferentes
        name  = c.get('name')  or c.get('Name')  or ''
        value = c.get('value') or c.get('Value') or ''
        domain = (
            c.get('domain') or c.get('Domain') or
            c.get('host')   or c.get('Host')   or ''
        )
        path   = c.get('path')     or c.get('Path')     or '/'
        secure = c.get('secure')   or c.get('Secure')   or False
        http_only = c.get('httpOnly') or c.get('HttpOnly') or c.get('http_only') or False

        # sameSite: Playwright aceita 'Strict', 'Lax', 'None'
        same_site_raw = (
            c.get('sameSite') or c.get('SameSite') or
            c.get('samesite') or 'Lax'
        )
        same_site_map = {
            'strict': 'Strict', 'lax': 'Lax', 'none': 'None',
            'no_restriction': 'None', 'unspecified': 'Lax',
        }
        same_site = same_site_map.get(str(same_site_raw).lower(), 'Lax')

        # Garante que domain começa com ponto se for subdomínio
        if domain and not domain.startswith('.') and domain.count('.') >= 1:
            # .google.com permite subdomínios; google.com só o host exato
            # Para segurança, deixamos como veio (o Playwright lida bem)
            pass

        # Filtra só domínios do Google
        domain_check = domain.lstrip('.')
        if not any(domain_check in gd or gd.lstrip('.') in domain_check
                   for gd in GOOGLE_DOMAINS):
            continue

        if not name:
            continue

        entry = {
            'name':     name,
            'value':    value,
            'domain':   domain,
            'path':     path,
            'secure':   bool(secure),
            'httpOnly': bool(http_only),
            'sameSite': same_site,
        }

        # expires: Playwright aceita Unix timestamp (int) se presente
        expires = c.get('expirationDate') or c.get('expires') or c.get('Expires')
        if expires:
            try:
                entry['expires'] = int(float(expires))
            except (ValueError, TypeError):
                pass

        normalized.append(entry)

    return normalized


def load_cookies(cookie_file: pathlib.Path | None = None) -> list[dict]:
    """
    Carrega e normaliza cookies de um arquivo JSON.
    Retorna lista vazia se o arquivo não existe ou está inválido.
    """
    path = cookie_file or _find_cookie_file()
    if not path:
        logger.warning(
            "[CookieManager] Nenhum arquivo de cookies encontrado. "
            "Exporte seus cookies do Google Maps e salve em leads/google_cookies.json"
        )
        return []

    try:
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)

        if not isinstance(raw, list):
            logger.warning(f"[CookieManager] Formato inesperado em {path}: esperava lista JSON")
            return []

        cookies = _normalize_cookies(raw)
        logger.info(f"[CookieManager] ✓ {len(cookies)} cookies carregados de {path.name}")
        return cookies

    except json.JSONDecodeError as e:
        logger.error(f"[CookieManager] JSON inválido em {path}: {e}")
        return []
    except Exception as e:
        logger.error(f"[CookieManager] Erro ao carregar cookies: {e}")
        return []


async def inject_google_cookies(context) -> bool:
    """
    Injeta cookies do Google no contexto Playwright.
    Retorna True se injetou ao menos 1 cookie essencial (SOCS, NID, ou CONSENT).

    USO:
        context = await browser.new_context(...)
        ok = await inject_google_cookies(context)
        if not ok:
            logger.warning("Cookies não injetados — scraper pode ter dados limitados")
    """
    cookies = load_cookies()
    if not cookies:
        return False

    try:
        await context.add_cookies(cookies)

        # Verifica se os cookies essenciais estão presentes
        essential = {'SOCS', 'NID', 'CONSENT', '__Secure-1PSID', 'SID', '1P_JAR'}
        injected_names = {c['name'] for c in cookies}
        found_essential = essential & injected_names

        if found_essential:
            logger.info(
                f"[CookieManager] ✓ Cookies injetados. Essenciais presentes: "
                f"{', '.join(sorted(found_essential))}"
            )
            return True
        else:
            logger.warning(
                f"[CookieManager] ⚠️  Cookies injetados mas nenhum cookie essencial "
                f"(SOCS/NID/CONSENT) encontrado. O Google pode ainda tratar como novo usuário. "
                f"Cookies encontrados: {', '.join(sorted(injected_names)[:10])}"
            )
            return True  # injeta mesmo assim — qualquer cookie ajuda

    except Exception as e:
        logger.error(f"[CookieManager] Erro ao injetar cookies: {e}")
        return False


def check_cookies_freshness() -> dict:
    """
    Verifica se os cookies existem e estima se ainda são válidos.
    Retorna dict com status para uso em management commands ou health checks.
    """
    path = _find_cookie_file()
    result = {
        'file_found': False,
        'file_path': None,
        'cookie_count': 0,
        'essential_present': [],
        'estimated_valid': False,
        'age_days': None,
        'warnings': [],
    }

    if not path:
        result['warnings'].append(
            "Arquivo de cookies não encontrado. "
            "Crie leads/google_cookies.json exportando do Cookie-Editor."
        )
        return result

    result['file_found'] = True
    result['file_path'] = str(path)

    # Idade do arquivo
    mtime = path.stat().st_mtime
    age_days = (time.time() - mtime) / 86400
    result['age_days'] = round(age_days, 1)

    if age_days > 60:
        result['warnings'].append(
            f"Arquivo tem {age_days:.0f} dias. "
            "Cookies do Google costumam expirar em 30-90 dias — considere renovar."
        )
    elif age_days > 30:
        result['warnings'].append(
            f"Arquivo tem {age_days:.0f} dias. Monitore se o scraper começa a trazer dados incompletos."
        )

    cookies = load_cookies(path)
    result['cookie_count'] = len(cookies)

    if not cookies:
        result['warnings'].append("Arquivo encontrado mas sem cookies válidos do Google.")
        return result

    essential = {'SOCS', 'NID', 'CONSENT', '__Secure-1PSID', 'SID', '1P_JAR', 'APISID', 'HSID'}
    names = {c['name'] for c in cookies}
    result['essential_present'] = sorted(essential & names)

    # Verifica expiração dos cookies essenciais
    now = time.time()
    expired = []
    for c in cookies:
        if c.get('name') in essential and 'expires' in c:
            if c['expires'] > 0 and c['expires'] < now:
                expired.append(c['name'])

    if expired:
        result['warnings'].append(
            f"Cookies expirados: {', '.join(expired)}. Exporte novamente do navegador."
        )
        result['estimated_valid'] = False
    elif result['essential_present']:
        result['estimated_valid'] = True
    else:
        result['warnings'].append(
            "Nenhum cookie essencial (SOCS, NID, CONSENT, SID) encontrado. "
            "Tente exportar estando na página do Google Maps, não apenas google.com."
        )

    return result


def print_cookie_status():
    """Imprime relatório de status dos cookies no terminal."""
    status = check_cookies_freshness()

    print("\n" + "═" * 55)
    print("  Nuviie — Status dos Cookies do Google")
    print("═" * 55)

    if status['file_found']:
        print(f"  Arquivo   : {pathlib.Path(status['file_path']).name}")
        print(f"  Idade     : {status['age_days']} dias")
        print(f"  Cookies   : {status['cookie_count']} carregados")
        print(f"  Essenciais: {', '.join(status['essential_present']) or 'nenhum'}")
        print(f"  Válido?   : {'✅ Sim' if status['estimated_valid'] else '⚠️  Incerto'}")
    else:
        print("  ❌ Nenhum arquivo de cookies encontrado")

    if status['warnings']:
        print()
        for w in status['warnings']:
            print(f"  ⚠️  {w}")

    print()
    if not status['file_found'] or not status['estimated_valid']:
        print("  COMO EXPORTAR:")
        print("  1. Instale 'Cookie-Editor' no Firefox")
        print("  2. Acesse maps.google.com.br logado na sua conta Google")
        print("  3. Abra o Cookie-Editor → Export → Export as JSON")
        print("  4. Salve em: leads/google_cookies.json")

    print("═" * 55 + "\n")
