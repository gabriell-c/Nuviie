"""
share_url_enrichment_patch.py — Patch de Enriquecimento via share.google
=========================================================================
Aplica automaticamente o patch no scraper.py para abrir o link
share.google/... de cada empresa e extrair TODOS os dados da página
expandida — que é muito mais completa que o box lateral do Maps.

POR QUE ISSO FUNCIONA:
  O link share.google/XXXX redireciona para uma URL do tipo:
    https://www.google.com/search?q=Nome+da+Empresa&...
  Essa página de busca mostra o "Knowledge Panel" completo da empresa,
  com TODOS os dados disponíveis: telefone, site, horários, endereço,
  categoria, redes sociais, fotos, avaliações, etc.

O PATCH ADICIONA:
  1. Função _enrich_from_share_url(context, share_url) → dict
     - Resolve o redirect do share.google para a URL final
     - Abre em nova aba Playwright
     - Faz scroll completo para carregar lazy-load
     - Extrai todos os dados via JS do Knowledge Panel
     - Extrai telefone, site, redes sociais, horários, avaliações

  2. Chamada da função dentro de _extract_place_async, logo após
     capturar share_url e antes de montar o dict final.
     Faz merge inteligente: dados do share_url preenchem campos vazios.

COMO APLICAR:
  python share_url_enrichment_patch.py

COMO REVERTER:
  Um backup .bak é criado automaticamente antes de qualquer alteração.
"""

# ══════════════════════════════════════════════════════════════════════════════
# BLOCO 1 — Função _enrich_from_share_url
# Inserida logo antes de "_extract_place_async"
# ══════════════════════════════════════════════════════════════════════════════

PATCH_1_ANCHOR = '''# ─── Substitua a função _extract_place_async inteira por esta ─────────────────

async def _extract_place_async('''

PATCH_1_NEW = '''# ─── Substitua a função _extract_place_async inteira por esta ─────────────────

# ---------------------------------------------------------------------------
# ✅ ENRIQUECIMENTO VIA share.google — extrai Knowledge Panel completo
# ---------------------------------------------------------------------------

_JS_EXTRACT_KNOWLEDGE_PANEL = r"""
() => {
    const R = {
        phone: null, website: null, address: null, category: null,
        hours: {}, instagram: null, facebook: null, youtube: null,
        twitter: null, linkedin: null, tiktok: null,
        bio: null, rating: null, review_count: null,
        price_range: null, amenities: [], name: null,
    };

    // ── Nome da empresa ───────────────────────────────────────────────────
    // Knowledge Panel: h2.qrShPb, div[data-attrid="title"], h3.LC20lb
    const nameEl =
        document.querySelector('h2.qrShPb span') ||
        document.querySelector('[data-attrid="title"] span') ||
        document.querySelector('div.SPZz6b h2') ||
        document.querySelector('h3.LC20lb');
    if (nameEl) R.name = nameEl.textContent.trim();

    // ── Categoria ─────────────────────────────────────────────────────────
    const catEl =
        document.querySelector('[data-attrid="subtitle"] span') ||
        document.querySelector('div.wwUB2c span') ||
        document.querySelector('span.YhemCb');
    if (catEl) R.category = catEl.textContent.trim();

    // ── Telefone ──────────────────────────────────────────────────────────
    // Knowledge Panel exibe telefone em [data-attrid*="phone"] ou span com ☎
    const phoneAttrs = document.querySelectorAll('[data-attrid*="phone"] span, [data-attrid*="telefone"] span');
    for (const el of phoneAttrs) {
        const t = el.textContent.trim();
        if (/[\d\(\)\-\+\s]{7,}/.test(t) && t.length < 30) { R.phone = t; break; }
    }
    // Fallback: link tel:
    if (!R.phone) {
        const telLink = document.querySelector('a[href^="tel:"]');
        if (telLink) R.phone = telLink.getAttribute('href').replace('tel:', '').trim();
    }
    // Fallback 2: texto com padrão de telefone brasileiro
    if (!R.phone) {
        const bodyText = document.body ? document.body.innerText : '';
        const telM = bodyText.match(/\(?\d{2}\)?\s?(?:9\s?\d{4}|\d{4})[-\s]?\d{4}/);
        if (telM) R.phone = telM[0];
    }

    // ── Website ───────────────────────────────────────────────────────────
    const siteEl =
        document.querySelector('[data-attrid*="website"] a') ||
        document.querySelector('[data-attrid*="site"] a') ||
        document.querySelector('a[data-ved][href^="http"]:not([href*="google"])');
    if (siteEl) {
        const href = siteEl.getAttribute('href') || '';
        // Remove redirect do Google (/url?q=...)
        const m = href.match(/[?&]q=(https?[^&]+)/);
        R.website = m ? decodeURIComponent(m[1]) : href;
    }

    // ── Endereço ──────────────────────────────────────────────────────────
    const addrEl =
        document.querySelector('[data-attrid*="address"] span') ||
        document.querySelector('[data-attrid*="endereco"] span') ||
        document.querySelector('span.LrzXr');
    if (addrEl) R.address = addrEl.textContent.trim();

    // ── Rating e contagem de reviews ──────────────────────────────────────
    const ratingEl =
        document.querySelector('span.Aq14fc') ||
        document.querySelector('[data-attrid*="rating"] span.Aq14fc') ||
        document.querySelector('div.BHMmbe');
    if (ratingEl) {
        const t = ratingEl.textContent.trim().replace(',', '.');
        const n = parseFloat(t);
        if (!isNaN(n) && n >= 1 && n <= 5) R.rating = n;
    }
    const reviewEl =
        document.querySelector('[data-attrid*="review_count"] span') ||
        document.querySelector('span.hqzQac span') ||
        document.querySelector('a[href*="review"] span');
    if (reviewEl) {
        const t = reviewEl.textContent.replace(/\D/g, '');
        if (t) R.review_count = parseInt(t, 10);
    }

    // ── Horários de funcionamento ─────────────────────────────────────────
    // Tenta extrair da tabela de horários no Knowledge Panel
    const dayMapKP = {
        'segunda': 'seg', 'terça': 'ter', 'terca': 'ter',
        'quarta': 'qua', 'quinta': 'qui', 'sexta': 'sex',
        'sábado': 'sab', 'sabado': 'sab', 'domingo': 'dom',
        'monday': 'seg', 'tuesday': 'ter', 'wednesday': 'qua',
        'thursday': 'qui', 'friday': 'sex', 'saturday': 'sab', 'sunday': 'dom',
    };
    // Rows de horários no KP: div[data-attrid*="hours"] ou table com dias
    const hoursRows = document.querySelectorAll(
        '[data-attrid*="hours"] tr, [data-attrid*="horario"] tr, ' +
        'div.t39EBf tr, table.eK4R0e tr'
    );
    for (const row of hoursRows) {
        const cells = row.querySelectorAll('td, li');
        if (cells.length < 2) continue;
        const dayText = cells[0].textContent.trim().toLowerCase();
        const hrsText = cells[1].textContent.trim();
        let key = null;
        for (const [dayPart, abbr] of Object.entries(dayMapKP)) {
            if (dayText.startsWith(dayPart)) { key = abbr; break; }
        }
        if (!key) continue;
        const hm = hrsText.match(/(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})/);
        if (/fechado|closed/i.test(hrsText)) R.hours[key] = 'Fechado';
        else if (/24\s*horas|24\s*hours/i.test(hrsText)) R.hours[key] = '00:00–23:59';
        else if (hm) R.hours[key] = hm[1] + '–' + hm[2];
        else if (hrsText) R.hours[key] = hrsText.slice(0, 20);
    }

    // ── Bio / Descrição ───────────────────────────────────────────────────
    const bioEl =
        document.querySelector('[data-attrid*="description"] span') ||
        document.querySelector('div.kno-rdesc span');
    if (bioEl) R.bio = bioEl.textContent.trim().slice(0, 800);

    // ── Redes sociais — links presentes no Knowledge Panel ────────────────
    const allLinks = document.querySelectorAll('a[href]');
    const bad = new Set(['explore','reel','reels','p','stories','tv','accounts','tags','share']);
    for (const a of allLinks) {
        const href = a.href || '';
        // Instagram
        if (!R.instagram && /instagram\.com\//.test(href)) {
            const m = href.match(/instagram\.com\/([A-Za-z0-9._]{1,50})\/?/);
            if (m && !bad.has(m[1].toLowerCase())) R.instagram = '@' + m[1];
        }
        // Facebook
        if (!R.facebook && /(?:facebook\.com|fb\.com|fb\.me)\//.test(href)) {
            if (!/facebook\.com\/(sharer|share|login|dialog)/.test(href))
                R.facebook = href;
        }
        // YouTube
        if (!R.youtube && /youtube\.com\/(channel|c\/|@|user\/)/.test(href)) {
            R.youtube = href;
        }
        // Twitter / X
        if (!R.twitter && /(?:twitter\.com|x\.com)\//.test(href)) {
            if (!/\/(intent|share|home)/.test(href)) R.twitter = href;
        }
        // LinkedIn
        if (!R.linkedin && /linkedin\.com\//.test(href)) {
            R.linkedin = href;
        }
        // TikTok
        if (!R.tiktok && /tiktok\.com\/@/.test(href)) {
            const m = href.match(/tiktok\.com\/@([A-Za-z0-9._]+)/);
            if (m) R.tiktok = '@' + m[1];
        }
    }

    // ── Faixa de preço ────────────────────────────────────────────────────
    const allText = document.body ? document.body.innerText : '';
    const priceM = allText.match(/\b([$€£]{1,4})\b/);
    if (priceM) R.price_range = priceM[1];

    // ── Amenidades ────────────────────────────────────────────────────────
    const amenityEls = document.querySelectorAll(
        '[data-attrid*="amenities"] span, [data-attrid*="attribute"] span, ' +
        'div.bnYBrd span, div.iP2t7d span'
    );
    const seenAm = new Set();
    for (const el of amenityEls) {
        const t = el.textContent.trim();
        if (t && t.length > 3 && t.length < 80 && !seenAm.has(t)) {
            seenAm.add(t);
            R.amenities.push(t);
        }
        if (R.amenities.length >= 30) break;
    }

    return R;
}
"""

async def _enrich_from_share_url(context, share_url: str) -> dict:
    """
    Abre o link share.google/... (ou maps.app.goo.gl/...) em nova aba,
    aguarda o redirect final, extrai TODOS os dados disponíveis no
    Knowledge Panel / página de pesquisa resultante.

    Retorna dict com campos extras (pode estar vazio em caso de falha).
    """
    import asyncio
    import re

    result = {}
    page = None
    try:
        from playwright.async_api import TimeoutError as PWTimeout

        page = await context.new_page()

        # Bloqueia apenas assets pesados — precisamos de todo o conteúdo
        await page.route(
            '**/*.{woff,woff2,ttf,otf,mp4,mp3,pdf,eot}',
            lambda r: r.abort()
        )

        logger.info(f"[Maps][ShareEnrich] Abrindo: {share_url}")

        # O share.google redireciona automaticamente — wait until networkidle
        # para garantir que a página final carregou
        try:
            await page.goto(share_url, wait_until='domcontentloaded', timeout=20000)
        except PWTimeout:
            logger.warning(f"[Maps][ShareEnrich] Timeout ao abrir share_url")
            return result

        # Aguarda redirect completar (share.google → google.com/maps/place/...)
        await asyncio.sleep(3)
        final_url = page.url
        logger.info(f"[Maps][ShareEnrich] URL final após redirect: {final_url[:120]}")

        # Se caiu em página de consentimento, aceita
        try:
            from leads.scraper import _handle_consent  # tenta import relativo
        except ImportError:
            pass
        else:
            await _handle_consent(page)
            await asyncio.sleep(1)

        # Aguarda h1 ou knowledge panel
        try:
            await page.wait_for_selector('h1, h2.qrShPb, [data-attrid="title"]', timeout=10000)
        except PWTimeout:
            logger.warning("[Maps][ShareEnrich] Knowledge Panel não encontrado")
            return result

        # Scroll progressivo para forçar lazy-load de todos os campos
        _scroll_kp = """(px) => {
            const p = document.querySelector('[role="main"]') ||
                      document.querySelector('.DxyBCb') ||
                      document.body;
            if (p) p.scrollTop = px;
            else window.scrollTo(0, px);
        }"""
        for step_px in [400, 800, 1500, 2500, 4000, 7000, 99999]:
            try:
                await page.evaluate(_scroll_kp, step_px)
                await asyncio.sleep(0.5)
            except Exception:
                pass
        await asyncio.sleep(1.5)

        # Expande dropdown de horários se disponível (mesma lógica do scraper principal)
        try:
            hours_btn = None
            for sel in [
                'div.OMl5r[jsaction*="openhours"][aria-expanded="false"]',
                'div[jsaction*="openhours"][aria-expanded="false"]',
                '[jsaction*="openhours"]',
                'button[aria-label*="Outros horários"]',
                'button[aria-label*="horário"]',
            ]:
                try:
                    candidates = await page.query_selector_all(sel)
                    for c in candidates:
                        if await c.is_visible():
                            hours_btn = c
                            break
                    if hours_btn:
                        break
                except Exception:
                    continue
            if hours_btn:
                await hours_btn.click()
                await asyncio.sleep(1.5)
                logger.info("[Maps][ShareEnrich] ✓ Dropdown horários expandido")
        except Exception:
            pass

        # Extrai via JS do Knowledge Panel
        try:
            kp_data = await page.evaluate(_JS_EXTRACT_KNOWLEDGE_PANEL)
            logger.info(
                f"[Maps][ShareEnrich] ✓ KP extraído: "
                f"tel={kp_data.get('phone')} | ig={kp_data.get('instagram')} | "
                f"hrs={bool(kp_data.get('hours'))} | rating={kp_data.get('rating')}"
            )
            result.update(kp_data)
        except Exception as e:
            logger.warning(f"[Maps][ShareEnrich] Falha JS extract: {e}")

        # Se a URL final é /maps/place/, extrai horários com JS específico do Maps
        if '/maps/place/' in final_url or '/maps/search/' in final_url:
            try:
                hours_dom = await page.evaluate(r"""
() => {
    const hours = {};
    const dayMap = {
        'segunda-feira':'seg','terça-feira':'ter','terca-feira':'ter',
        'quarta-feira':'qua','quinta-feira':'qui','sexta-feira':'sex',
        'sábado':'sab','sabado':'sab','domingo':'dom'
    };
    const rows = document.querySelectorAll('table.eK4R0e tr.y0skZc, tr.y0skZc');
    for (const row of rows) {
        const cells = row.querySelectorAll('td');
        if (cells.length < 2) continue;
        const dayText = cells[0].textContent.trim().toLowerCase();
        const hrsText = cells[1].textContent.trim();
        const key = dayMap[dayText];
        if (!key) continue;
        if (/atendimento\s*24\s*horas|aberto\s*24/i.test(hrsText)) {
            hours[key] = '00:00–23:59';
        } else if (/fechado|closed/i.test(hrsText)) {
            hours[key] = 'Fechado';
        } else {
            const hm = hrsText.match(/(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})/);
            if (hm) hours[key] = hm[1] + '–' + hm[2];
            else if (hrsText.length > 3) hours[key] = hrsText.slice(0, 20);
        }
    }
    const openEl = document.querySelector('[class*="ZjTjCd"], [class*="o0Svhf"]');
    if (openEl) {
        const txt = openEl.textContent.trim();
        if (txt) hours.status_atual = txt.slice(0, 80);
        hours.aberto_agora = !/fechado/i.test(txt);
    }
    return hours;
}
                """)
                if hours_dom and len([k for k in hours_dom if k not in ('status_atual', 'aberto_agora')]) > 0:
                    result['hours'] = hours_dom
                    logger.info(f"[Maps][ShareEnrich] ✓ Horários do DOM Maps: {list(hours_dom.keys())}")
            except Exception:
                pass

            # Extrai reviews da página do Maps se disponível
            try:
                reviews_extra = await page.evaluate("""
() => {
    const reviews = [];
    const seen = new Set();
    const containers = [
        ...document.querySelectorAll('[data-review-id]'),
        ...document.querySelectorAll('div.jftiEf'),
    ];
    for (const c of containers) {
        if (reviews.length >= 10) break;
        const rev = {};
        const authorEl = c.querySelector('div[class*="d4r55"]') || c.querySelector('.d4r55');
        if (authorEl) rev.author = authorEl.textContent.trim();
        const ratingEl = c.querySelector('[aria-label*="estrela"]') || c.querySelector('[aria-label*="star"]');
        if (ratingEl) {
            const m = (ratingEl.getAttribute('aria-label') || '').match(/(\d)/);
            if (m) rev.rating = parseInt(m[1]);
        }
        const dateEl = c.querySelector('span[class*="rsqaWe"]') || c.querySelector('span[class*="xRkPPb"]');
        if (dateEl) rev.date = dateEl.textContent.trim();
        const textEl = c.querySelector('span[class*="wiI7pd"]');
        if (textEl) rev.text = textEl.textContent.trim().slice(0, 1000);
        if (!rev.author && !rev.text && !rev.rating) continue;
        const key = [(rev.author||'').toLowerCase(), (rev.date||''), (rev.text||'').slice(0,60)].join('|');
        if (seen.has(key)) continue;
        seen.add(key);
        reviews.push(rev);
    }
    return reviews;
}
                """)
                if reviews_extra:
                    result['recent_reviews_extra'] = reviews_extra
                    logger.info(f"[Maps][ShareEnrich] ✓ {len(reviews_extra)} reviews extras")
            except Exception:
                pass

        # Extrai og:image da página de resultado
        try:
            og_img = await page.evaluate("""
() => {
    const og = document.querySelector('meta[property="og:image"]');
    if (og) return og.getAttribute('content');
    const img = document.querySelector('button.aoRNLd img') ||
                document.querySelector('.RZ66Rb img') ||
                document.querySelector('img.t2cCgb');
    return img && img.src && !img.src.startsWith('data:') ? img.src : null;
}
            """)
            if og_img:
                result['og_image_extra'] = og_img
        except Exception:
            pass

    except Exception as e:
        logger.warning(f"[Maps][ShareEnrich] Erro geral: {e}")
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass

    return result


async def _extract_place_async('''

# ══════════════════════════════════════════════════════════════════════════════
# BLOCO 2 — Chamada de _enrich_from_share_url e merge dentro de _extract_place_async
# Substituído logo após captura do share_url e antes de montar js_data
# ══════════════════════════════════════════════════════════════════════════════

PATCH_2_OLD = """        share_final = share_url or js_data.get('share_url') or _extract_share_url(
            BeautifulSoup('<html/>', 'html.parser'), ''
        )"""

PATCH_2_NEW = '''        share_final = share_url or js_data.get('share_url') or _extract_share_url(
            BeautifulSoup('<html/>', 'html.parser'), ''
        )

        # ── ENRIQUECIMENTO VIA share.google ───────────────────────────────────
        # Abre o link de compartilhamento em nova aba para extrair dados
        # completos do Knowledge Panel / página de busca — muito mais rico
        # que o box lateral do Maps.
        enrich_data = {}
        if share_final and share_final.startswith('http'):
            try:
                enrich_data = await _enrich_from_share_url(context, share_final)
                logger.info(
                    f"[Maps][ShareEnrich] Merge: "
                    f"tel={enrich_data.get('phone')} | "
                    f"ig={enrich_data.get('instagram')} | "
                    f"site={enrich_data.get('website')} | "
                    f"hrs={bool(enrich_data.get('hours'))} | "
                    f"rating={enrich_data.get('rating')}"
                )
            except Exception as _ee:
                logger.warning(f"[Maps][ShareEnrich] Erro no enriquecimento: {_ee}")

        def _best(primary, secondary):
            """Retorna primary se não-vazio, senão secondary."""
            if primary is not None and primary != '' and primary != [] and primary != {}:
                return primary
            return secondary

        # Merge: dados do scrape principal têm prioridade;
        # enrich_data preenche campos que faltaram
        if enrich_data:
            phone_raw   = _best(phone_raw,   enrich_data.get('phone'))
            raw_website = _best(raw_website, enrich_data.get('website'))

            # Recalcula normalized_phone se veio do enrich
            if not normalized and phone_raw:
                normalized = normalize_phone(phone_raw)

            # Recalcula tipo do website se veio do enrich
            if not (js_data.get('website')) and raw_website:
                website_type = detect_website_type(raw_website)

            # Redes sociais: preenche lacunas
            instagram = _best(instagram, enrich_data.get('instagram'))
            facebook  = _best(facebook,  enrich_data.get('facebook'))
            youtube   = _best(youtube,   enrich_data.get('youtube'))
            twitter   = _best(twitter,   enrich_data.get('twitter'))
            linkedin  = _best(linkedin,  enrich_data.get('linkedin'))
            if not tiktok_val:
                tiktok_val = enrich_data.get('tiktok')

            # Horários: se o scrape principal não capturou, usa do enrich
            if not hours_clean and enrich_data.get('hours'):
                _KEY_MAP_E = {
                    'seg':'seg','ter':'ter','qua':'qua',
                    'qui':'qui','sex':'sex','sab':'sab','dom':'dom',
                }
                for k, v in enrich_data['hours'].items():
                    if k in _KEY_MAP_E:
                        hours_clean[_KEY_MAP_E[k]] = v
                    else:
                        hours_clean[k] = v
                logger.info(f"[Maps][ShareEnrich] Horários preenchidos via enrich: {list(hours_clean.keys())}")

            # Reviews extras
            if not reviews_js and enrich_data.get('recent_reviews_extra'):
                reviews_js = enrich_data['recent_reviews_extra']
                logger.info(f"[Maps][ShareEnrich] Reviews preenchidas via enrich: {len(reviews_js)}")

            # Foto de perfil
            if not profile_pic and enrich_data.get('og_image_extra'):
                profile_pic = enrich_data['og_image_extra']

            # Rating e review_count: usa o maior valor (mais confiável)
            enrich_rating = enrich_data.get('rating')
            enrich_rc     = enrich_data.get('review_count')
            if enrich_rating and (not rating or enrich_rating > rating):
                rating = enrich_rating
            if enrich_rc and (not review_count or enrich_rc > review_count):
                review_count = enrich_rc

            # Bio
            if not (js_data.get('bio') or '').strip() and enrich_data.get('bio'):
                js_data['bio'] = enrich_data['bio']

            # Amenidades
            if not js_data.get('amenities') and enrich_data.get('amenities'):
                js_data['amenities'] = enrich_data['amenities']

            # Price range
            if not js_data.get('price_range') and enrich_data.get('price_range'):
                js_data['price_range'] = enrich_data['price_range']

            # Normaliza instagram do enrich
            if instagram and not instagram.startswith('@'):
                instagram = '@' + instagram
            # Filtra handles ruins
            if instagram:
                bad_ig = {'explore','reel','reels','p','stories','tv','accounts','tags','share'}
                if instagram.lstrip('@').lower() in bad_ig:
                    instagram = None'''


# ══════════════════════════════════════════════════════════════════════════════
# Script de aplicação automática
# ══════════════════════════════════════════════════════════════════════════════

def apply_patch():
    import pathlib
    import sys

    scraper_path = pathlib.Path(__file__).parent / 'scraper.py'
    if not scraper_path.exists():
        print(f"❌  scraper.py não encontrado em: {scraper_path}")
        print("   Coloque este arquivo na mesma pasta do scraper.py e tente novamente.")
        sys.exit(1)

    content = scraper_path.read_text(encoding='utf-8')
    original = content
    # Normaliza CRLF→LF para matching das âncoras
    content = content.replace('\r\n', '\n')

    patches = [
        (
            'Patch 1 — Adiciona função _enrich_from_share_url',
            PATCH_1_ANCHOR,
            PATCH_1_NEW,
        ),
        (
            'Patch 2 — Chamada do enriquecimento + merge dentro de _extract_place_async',
            PATCH_2_OLD,
            PATCH_2_NEW,
        ),
    ]

    applied = []
    skipped = []
    errors  = []

    for name, old, new in patches:
        if old not in content:
            if new in content:
                skipped.append(f"  ⏭  {name} — já aplicado, pulando")
            else:
                errors.append(
                    f"  ❌  {name} — trecho original não encontrado.\n"
                    f"      Verifique se o scraper.py é a versão v8/v9/v10 correta."
                )
            continue

        count = content.count(old)
        if count > 1:
            errors.append(f"  ❌  {name} — trecho encontrado {count}x (ambíguo), aplique manualmente")
            continue

        content = content.replace(old, new, 1)
        applied.append(f"  ✅  {name}")

    print("\n" + "═" * 60)
    print("  Nuviie — Patch de Enriquecimento via share.google")
    print("═" * 60)

    if errors:
        print("\n  ERROS:")
        for e in errors:
            print(e)

    if skipped:
        print("\n  JÁ APLICADOS:")
        for s in skipped:
            print(s)

    if applied:
        backup = scraper_path.with_suffix('.py.bak')
        backup.write_text(original, encoding='utf-8')
        print(f"\n  Backup salvo em: {backup.name}")

        scraper_path.write_text(content, encoding='utf-8')
        print("\n  APLICADOS COM SUCESSO:")
        for a in applied:
            print(a)

        print("\n  EFEITO:")
        print("  → Para cada empresa scrapeada, o scraper vai agora:")
        print("    1. Extrair dados do box lateral do Maps (como antes)")
        print("    2. Abrir o link share.google em nova aba")
        print("    3. Esperar o redirect para a página de resultado completa")
        print("    4. Extrair TODOS os dados do Knowledge Panel")
        print("    5. Mesclar: dados existentes têm prioridade, campos vazios são preenchidos")
        print()
        print("  OBSERVAÇÃO:")
        print("  → O enriquecimento adiciona ~5-8s por empresa (nova aba extra).")
        print("  → Se share_url não estiver disponível, o enriquecimento é pulado.")
        print("  → Logs: procure por [Maps][ShareEnrich] nos logs do Django.")
    else:
        print("\n  Nenhuma alteração necessária.")

    if errors:
        print("\n  ⚠️  Alguns patches falharam — veja ERROS acima.")
        sys.exit(1)

    print("═" * 60 + "\n")


if __name__ == '__main__':
    apply_patch()
