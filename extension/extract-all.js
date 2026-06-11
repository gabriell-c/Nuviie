/* global NuviieMaps */
window.NuviieMaps = window.NuviieMaps || {};

NuviieMaps.extractAll = () => {
    const R = {
        name: null, category: null, phone: null, address: null,
        website: null, rating: null, review_count: null,
        instagram: null, facebook: null, youtube: null, twitter: null,
        linkedin: null, tiktok: null, whatsapp_link: null,
        bio: null, hours: {}, share_url: null, og_image: null,
        maps_url: null, price_range: null, plus_code: null,
        amenities: [], popular_times: null, total_photos: null,
        // v12: novos campos
        latitude: null, longitude: null, cid: null, kgmid: null,
        order_online: null, menu: null, reservations: null,
        coordinates: null,
    };

    // ── v12: KGMID — Knowledge Graph Machine ID ───────────────────────────────
    // É o identificador mais estável do Google (/g/11abc123)
    // Extraído de: URL canônica, link[rel=canonical], APP_INITIALIZATION_STATE
    try {
        const canonical = document.querySelector('link[rel="canonical"]');
        if (canonical) {
            const m = canonical.href.match(/\/maps\/place\/[^/]+\/(\/g\/[A-Za-z0-9_]+)/);
            if (m) R.kgmid = m[1];
        }
    } catch(e) {}
    if (!R.kgmid) {
        // Busca na URL atual
        const urlM = window.location.href.match(/\/(\/g\/[A-Za-z0-9_]+)/);
        if (urlM) R.kgmid = urlM[1];
    }
    if (!R.kgmid) {
        // Busca em data-pid (place id) ou data-cid em elementos do DOM
        for (const el of document.querySelectorAll('[data-pid]')) {
            const pid = el.getAttribute('data-pid') || '';
            if (pid.startsWith('/g/')) { R.kgmid = pid; break; }
        }
    }

    // ── v12: CID — Customer ID numérico do Google ────────────────────────────
    // Identificador numérico permanente de ~19 dígitos
    try {
        // Método 1: data-cid no DOM
        for (const el of document.querySelectorAll('[data-cid]')) {
            const cid = el.getAttribute('data-cid') || '';
            if (/^\d{10,20}$/.test(cid)) { R.cid = cid; break; }
        }
        // Método 2: URL atual (formato ?cid=NUMERO)
        if (!R.cid) {
            const cidM = window.location.href.match(/[?&;]cid=(\d+)/);
            if (cidM) R.cid = cidM[1];
        }
        // Método 3: Hex pairs no URL → CID decimal
        // URL Maps: /maps/place/NAME/0xHEX:0xHEX → segundo hex é o CID
        if (!R.cid) {
            const hexM = window.location.href.match(/\/maps\/place\/[^/]+\/0x[0-9a-f]+:0x([0-9a-f]+)/i);
            if (hexM) {
                try {
                    R.cid = BigInt('0x' + hexM[1]).toString();
                } catch(e) {}
            }
        }
    } catch(e) {}

    // ── v12: Latitude e Longitude — da URL canônica ──────────────────────────
    // O Google Maps sempre inclui @lat,lng,zoom na URL do lugar
    try {
        const latLngM = window.location.href.match(/@(-?\d+\.\d+),(-?\d+\.\d+),\d+/);
        if (latLngM) {
            R.latitude = parseFloat(latLngM[1]);
            R.longitude = parseFloat(latLngM[2]);
        }
        // Fallback: formato !3dlat!4dlng
        if (!R.latitude) {
            const m2 = window.location.href.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/);
            if (m2) {
                R.latitude = parseFloat(m2[1]);
                R.longitude = parseFloat(m2[2]);
            }
        }
        if (R.latitude && R.longitude) {
            R.coordinates = { lat: R.latitude, lng: R.longitude };
        }
    } catch(e) {}

    // ── v12: Order online / Menu / Reservations ───────────────────────────────
    // Botões de ação na ficha do Maps
    try {
        // Pedido online: iFood, Rappi, "Fazer pedido", etc.
        const orderSelectors = [
            'a[href*="ifood"]', 'a[href*="rappi"]', 'a[href*="ubereats"]',
            'a[href*="deliveroo"]', 'a[href*="aiqfome"]',
            'a[aria-label*="Pedir"]', 'a[aria-label*="pedido"]',
            'a[aria-label*="Fazer pedido"]', 'a[data-item-id*="order"]',
            'button[aria-label*="Pedir"]', 'button[aria-label*="pedido"]',
        ];
        for (const sel of orderSelectors) {
            const el = document.querySelector(sel);
            if (el) { R.order_online = el.href || el.getAttribute('data-href') || 'disponível'; break; }
        }

        // Cardápio/Menu
        const menuSelectors = [
            'a[data-item-id*="menu"]', 'a[aria-label*="cardápio"]',
            'a[aria-label*="menu"]', 'a[aria-label*="Menu"]',
            'a[href*="menu"]',
        ];
        for (const sel of menuSelectors) {
            const el = document.querySelector(sel);
            if (el) { R.menu = el.href || el.getAttribute('data-href') || 'disponível'; break; }
        }

        // Reservas
        const resSelectors = [
            'a[data-item-id*="reserv"]', 'a[aria-label*="Reservar"]',
            'a[aria-label*="reserv"]', 'a[href*="reserve"]',
            'a[href*="opentable"]', 'a[href*="resy.com"]',
        ];
        for (const sel of resSelectors) {
            const el = document.querySelector(sel);
            if (el) { R.reservations = el.href || el.getAttribute('data-href') || 'disponível'; break; }
        }
    } catch(e) {}

    // ── v12: Popular Times ────────────────────────────────────────────────────
    // Extrai padrões de movimento por dia/hora quando disponíveis
    try {
        const popularTimesData = {};
        const dayMap = {
            'domingo': 'dom', 'segunda-feira': 'seg', 'segunda': 'seg',
            'terça-feira': 'ter', 'terca-feira': 'ter', 'terça': 'ter',
            'quarta-feira': 'qua', 'quarta': 'qua',
            'quinta-feira': 'qui', 'quinta': 'qui',
            'sexta-feira': 'sex', 'sexta': 'sex',
            'sábado': 'sab', 'sabado': 'sab',
        };
        // popular times ficam em divs com aria-label "X% ocupado às HH:MM"
        const ptEls = document.querySelectorAll('[aria-label*="ocupado"], [aria-label*="busy"], [aria-label*="lotado"]');
        for (const el of ptEls) {
            const lbl = el.getAttribute('aria-label') || '';
            // "42% ocupado às 18:00 na segunda-feira"
            const m = lbl.match(/(\d+)%.*?(\d{1,2}:\d{2}).*?(segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo)/i);
            if (m) {
                const pct = parseInt(m[1]);
                const hour = m[2];
                const dayKey = dayMap[m[3].toLowerCase()] || m[3].toLowerCase().slice(0,3);
                if (!popularTimesData[dayKey]) popularTimesData[dayKey] = {};
                popularTimesData[dayKey][hour] = pct;
            }
        }
        if (Object.keys(popularTimesData).length > 0) {
            R.popular_times = popularTimesData;
        }
    } catch(e) {}

    const bad = new Set(['explore','reel','reels','p','stories','tv','accounts',
                         'tags','share','sharer','intent','home','watch','results',
                         'search','jobs','feed','ads','about','legal','privacy',
                         'support','notifications','explore','highlights']);

    // ── Nome ──────────────────────────────────────────────────────────────────
    // ATENÇÃO: document.querySelector('h1') pega o PRIMEIRO h1 da página, que
    // pode ser o cabeçalho "Resultados" da lista de busca (lateral esquerda),
    // e não o nome do estabelecimento (que fica no painel de detalhes).
    // Por isso priorizamos h1 dentro do painel de detalhes (role="main") e,
    // se ainda assim vier "Resultados"/"Results", tratamos como inválido.
    const nameBad = new Set(['resultados', 'results', 'resultado']);
    let h1 = document.querySelector('[role="main"] h1.DUwDvf')
          || document.querySelector('[role="main"] h1')
          || document.querySelector('h1.DUwDvf')
          || document.querySelector('h1');
    if (h1) {
        const candidate = h1.textContent.trim();
        if (candidate && !nameBad.has(candidate.toLowerCase())) {
            R.name = candidate;
        }
    }

    // ── og:image e foto principal da ficha ───────────────────────────────────
    const og = document.querySelector('meta[property="og:image"]');
    if (og && og.content) R.og_image = og.content;
    // Fallback: imagem hero do topo da ficha (button.aoRNLd > img)
    if (!R.og_image) {
        const heroImg = document.querySelector('button.aoRNLd img, .RZ66Rb img');
        if (heroImg && heroImg.src && !heroImg.src.includes('data:')) {
            R.og_image = heroImg.src;
        }
    }

    // ── Categoria ─────────────────────────────────────────────────────────────
    // O botão de categoria fica logo abaixo do h1 — múltiplos seletores por segurança
    const notCat = new Set(['Rotas','Salvar','Compartilhar','Avaliar','Ligar','Enviar',
                    'Sugerir','Adicionar','Ordenar','Pesquisar','Fotos','Avaliações',
                    'Sobre','Visão geral','Serviços','Produtos']);
    const catCandidates = [
        document.querySelector('button[jsaction*="category"]'),
        document.querySelector('[jsan*="category"]'),
        document.querySelector('div.fontBodyMedium button.DkEaL'),
        document.querySelector('.LBgpqf button'),
        document.querySelector('.skqShb button'),
        // Estrutura nova: span.fontBodyMedium logo após o h1
        (() => {
            const spans = document.querySelectorAll('span.fontBodyMedium');
            for (const s of spans) {
                const btn = s.querySelector('button') || s;
                const t = btn.textContent.trim();
                if (t && t.length > 2 && t.length < 80 && !notCat.has(t)) return btn;
            }
            return null;
        })(),
        // Fallback: primeiro button[jsaction] após h1 que não seja ação conhecida
        (() => {
            const h1el = document.querySelector('h1');
            if (!h1el) return null;
            let el = h1el.nextElementSibling;
            for (let i = 0; i < 5 && el; i++, el = el.nextElementSibling) {
                const btn = el.querySelector('button') || (el.tagName === 'BUTTON' ? el : null);
                if (btn) {
                    const t = btn.textContent.trim();
                    if (t && !notCat.has(t) && t.length < 80) return btn;
                }
            }
            return null;
        })(),
    ];
    for (const catEl of catCandidates) {
        if (!catEl) continue;
        const catText = catEl.textContent.trim();
        if (catText && !notCat.has(catText) && catText.length > 2 && catText.length < 80) {
            R.category = catText;
            break;
        }
    }

    // ── Rating e total de reviews — via seletores diretos (mais confiável) ─────
    // O Google Maps exibe o rating em span.ceNzKf e total em button com aria-label
    if (!R.rating) {
        const ratingEl =
            document.querySelector('span.ceNzKf') ||
            document.querySelector('span.kvMYJc') ||
            document.querySelector('div.F7nice span[aria-hidden="true"]');
        if (ratingEl) {
            const n = parseFloat((ratingEl.textContent || '').trim().replace(',', '.'));
            if (!isNaN(n) && n >= 1 && n <= 5) R.rating = n;
        }
    }
    if (!R.review_count) {
        // Botão "XXX avaliações" no topo da ficha
        const rcEl =
            document.querySelector('button[aria-label*="avaliações"] span') ||
            document.querySelector('span.RDApEe') ||
            document.querySelector('span[aria-label*="avaliações"]') ||
            document.querySelector('div.F7nice span span');
        if (rcEl) {
            const txt = (rcEl.getAttribute('aria-label') || rcEl.textContent || '').replace(/\D/g, '');
            if (txt) {
                const n = parseInt(txt, 10);
                if (!isNaN(n) && n > 0) R.review_count = n;
            }
        }
    }

    // ── Aria-labels: varre todos para extrair phone, address, hours, rating ───
    const labelEls = document.querySelectorAll('[aria-label]');
    for (const el of labelEls) {
        const lbl = el.getAttribute('aria-label') || '';
        const lblL = lbl.toLowerCase();

        // Telefone
        if (!R.phone && (lblL.includes('telefone') || lblL.includes('phone'))) {
            const m = lbl.match(/[\d\s()\-\+]{7,}/);
            if (m) R.phone = m[0].trim();
        }

        // Endereço
        if (!R.address && (lblL.includes('endereço') || lblL.includes('address'))) {
            let addr = lbl.replace(/endereço:?/i,'').replace(/address:?/i,'').trim();
            if (addr.length > 5) R.address = addr;
        }

        // Rating
        if (!R.rating) {
            const rm = lbl.match(/([1-5][.,]\d)\s*(?:estrelas?|stars?)/i);
            if (rm) R.rating = parseFloat(rm[1].replace(',','.'));
        }

        // Review count — trata "1.203" e "1,203" corretamente
        if (!R.review_count) {
            const rcm = lbl.match(/([\d][.\d,]*[\d]|[\d]+)\s*(?:avaliações|avaliação|reviews?|comentários)/i);
            if (rcm) {
                const digits = rcm[1].replace(/[^\d]/g,'');
                if (digits) {
                    const n = parseInt(digits, 10);
                    if (!isNaN(n) && n > 0) R.review_count = n;
                }
            }
        }

        // Horários — linha com múltiplos dias
        const dayMatches = [...lbl.matchAll(
            /(segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo)[\s\-feira]*\s*:?\s*([\d:–\-\s]+|fechado|aberto\s*24\s*horas|atendimento\s*24\s*horas)/gi
        )];
        if (dayMatches.length >= 2) {
            const dayMap = {
                'segunda':'seg','terça':'ter','terca':'ter',
                'quarta':'qua','quinta':'qui','sexta':'sex',
                'sábado':'sab','sabado':'sab','domingo':'dom'
            };
            for (const [, rawDay, rawHrs] of dayMatches) {
                const key = dayMap[rawDay.toLowerCase().trim()];
                if (!key || R.hours[key]) continue;
                const hm = rawHrs.match(/(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})/);
                if (hm) R.hours[key] = hm[1] + '–' + hm[2];
                else if (/fechado|closed/i.test(rawHrs)) R.hours[key] = 'Fechado';
                else if (/24\s*hora|atendimento\s*24/i.test(rawHrs)) R.hours[key] = '00:00–23:59';
            }
        }
        // Horários — formato "dia, HH:MM–HH:MM" ou "dia, Fechado" (aria-label individual)
        const singleDay = lbl.match(/^(segunda[\-\s]?feira|terça[\-\s]?feira|quarta[\-\s]?feira|quinta[\-\s]?feira|sexta[\-\s]?feira|sábado|sabado|domingo),?\s+(.+)/i);
        if (singleDay) {
            const dayMapFull = {
                'segunda-feira':'seg','segunda feira':'seg','terça-feira':'ter','terca-feira':'ter',
                'terça feira':'ter','terca feira':'ter','quarta-feira':'qua','quarta feira':'qua',
                'quinta-feira':'qui','quinta feira':'qui','sexta-feira':'sex','sexta feira':'sex',
                'sábado':'sab','sabado':'sab','domingo':'dom'
            };
            const dkey = dayMapFull[singleDay[1].toLowerCase().trim()];
            if (dkey && !R.hours[dkey]) {
                const rawHrs2 = singleDay[2];
                // Suporte a 2 períodos: "08:00–11:30 / 14:00–17:00"
                const allP2 = [...rawHrs2.matchAll(/(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})/g)];
                if (allP2.length >= 2) R.hours[dkey] = allP2.map(p => p[1]+'–'+p[2]).join(' / ');
                else if (allP2.length === 1) R.hours[dkey] = allP2[0][1] + '–' + allP2[0][2];
                else if (/fechado|closed/i.test(rawHrs2)) R.hours[dkey] = 'Fechado';
                else if (/24\s*hora|atendimento\s*24/i.test(rawHrs2)) R.hours[dkey] = '00:00–23:59';
            }
        }
    }

    // ── Bio / descrição ───────────────────────────────────────────────────────
    for (const sel of ['[aria-label*="Sobre"]','[aria-label*="Resumo"]',
                       '[data-item-id*="editorial"]',
                       'div.PYvSYb','div.ZD2Oce','span.HlvSq',
                       'div.iP2t7d > span', 'span.P5Bobd']) {
        const el = document.querySelector(sel);
        if (el) {
            const t = el.textContent.trim();
            // Relaxado: mínimo 5 chars (era 20) para não perder bios curtas
            if (t.length > 5 && t.length < 1000) { R.bio = t; break; }
        }
    }

    // ── Website e redes sociais — todos os <a href> + texto da página ────────
    // ATENÇÃO: usamos document.querySelectorAll aqui pegaria também links da
    // LISTA de resultados (lateral esquerda) e de anúncios/cards "Patrocinado",
    // que ficam no DOM mesmo enquanto navegamos entre lugares. Isso fazia o
    // mesmo Instagram (de um anúncio fixo) "vazar" para todos os leads.
    // Por isso restringimos a busca ao painel de detalhes do lugar.
    const detailRoot = document.querySelector('[role="main"]') || document.body;

    // ── "Resultados da Web" — links extras (Instagram, LinkedIn, Facebook etc.)
    // ficam dentro de um <iframe src="/search?q=..."> que é MESMA ORIGEM
    // (google.com), então conseguimos acessar contentDocument sem CORS.
    // ATENÇÃO: esse iframe é uma SPA e às vezes NÃO é recriado/recarregado a
    // tempo quando navegamos pra outro lugar — seu conteúdo pode ainda ser o
    // do lugar ANTERIOR e "vazar" pros leads seguintes (ex: mesmo Instagram
    // repetido em vários leads diferentes). Para evitar isso, só confiamos no
    // iframe se o `src` dele (parâmetro q=) bater com o nome do lugar atual.
    let webResultsLinks = [];
    let webResultsDoc = null;
    try {
        const normalize = (s) => (s || '')
            .normalize('NFD').replace(/[\u0300-\u036f]/g, '') // remove acentos
            .toLowerCase()
            .replace(/[^a-z0-9 ]/g, ' ')
            .trim();
        const nameNorm = normalize(R.name);
        // primeira "palavra forte" do nome (>=3 letras), pra comparar com a query do iframe
        const nameToken = nameNorm.split(' ').find((w) => w.length >= 3) || '';

        for (const frame of detailRoot.querySelectorAll('iframe.rvN3ke, iframe[src^="/search"]')) {
            try {
                let frameQuery = '';
                try { frameQuery = normalize(decodeURIComponent(frame.getAttribute('src') || '')); } catch (e) {
                    frameQuery = normalize(frame.getAttribute('src') || '');
                }
                // Se não conseguimos confirmar que o iframe é do lugar atual, ignoramos
                // (melhor não ter o dado do que vazar o de outro lugar).
                if (nameToken && !frameQuery.includes(nameToken)) continue;

                const fdoc = frame.contentDocument || frame.contentWindow?.document;
                if (fdoc) {
                    webResultsLinks = webResultsLinks.concat([...fdoc.querySelectorAll('a[href]')]);
                    webResultsDoc = fdoc;
                }
            } catch (e) { /* iframe ainda não carregou ou bloqueado */ }
        }
    } catch (e) {}

    // ── Bio fallback via "Resultados da Web" ──────────────────────────────────
    // Algumas empresas têm uma descrição (texto entre aspas, "De [Nome]: '...'")
    // que só aparece nos resultados de busca normais do Google, não na aba
    // "Sobre" do painel do Maps. Como o iframe.rvN3ke é a mesma página de busca
    // (mesma origem), conseguimos ler esse texto dali.
    if (!R.bio && webResultsDoc) {
        try {
            const wrText = webResultsDoc.body.innerText || '';
            const bioM = wrText.match(/De\s+[^\n:]{2,120}[:\n]\s*"([^"\n]{15,800})"/i)
                      || wrText.match(/"([^"\n]{30,800})"/);
            if (bioM) R.bio = bioM[1].trim();
        } catch (e) { /* ignore */ }
    }

    // Primeiro: links diretos (painel principal + iframe "Resultados da Web", se confirmado fresco)
    for (const a of [...detailRoot.querySelectorAll('a[href]'), ...webResultsLinks]) {
        let href = (a.href || '').trim();
        if (!href || href.startsWith('javascript:')) continue;

        // Links de "Resultados da Web" às vezes vêm como redirect do Google
        // (/url?q=https%3A%2F%2Fbr.linkedin.com%2Fin%2F...&...). O texto visível
        // do card pode estar truncado ("https://br.linkedin.com › ..."), mas o
        // href real do redirect contém a URL completa — resolvemos isso aqui.
        const redirectM = href.match(/[?&]q=([^&]+)/);
        if (redirectM && /\/url\?/.test(href)) {
            try { href = decodeURIComponent(redirectM[1]); } catch (e) { /* ignore */ }
        }

        // Instagram
        if (!R.instagram) {
            const m = href.match(/instagram\.com\/([A-Za-z0-9._]{2,50})/);
            if (m && !bad.has(m[1].toLowerCase()))
                R.instagram = '@' + m[1].replace(/\/$/,'');
        }
        // Facebook
        if (!R.facebook) {
            const m = href.match(/facebook\.com\/([A-Za-z0-9._\-]{2,80})/);
            if (m && !bad.has(m[1].toLowerCase()))
                R.facebook = href.replace(/[?#].*/,'');
        }
        // YouTube
        if (!R.youtube) {
            const m = href.match(/youtube\.com\/(?:channel\/|c\/|@)([A-Za-z0-9._\-]{2,80})/);
            if (m && !bad.has(m[1].toLowerCase()))
                R.youtube = href.replace(/[?#].*/,'');
        }
        // Twitter/X
        if (!R.twitter) {
            const m = href.match(/(?:twitter|x)\.com\/([A-Za-z0-9._]{2,50})/);
            if (m && !bad.has(m[1].toLowerCase()))
                R.twitter = href.replace(/[?#].*/,'');
        }
        // LinkedIn — qualquer subdomínio (br.linkedin.com, www.linkedin.com, etc),
        // perfis pessoais (/in/) ou de empresa (/company/)
        if (!R.linkedin) {
            const m = href.match(/linkedin\.com\/(in|company)\/([A-Za-z0-9._\-]{2,80})/);
            if (m && !bad.has(m[2].toLowerCase()))
                R.linkedin = href.replace(/[?#].*/,'');
        }
        // WhatsApp
        if (!R.phone) {
            const m = href.match(/wa\.me\/(\d{10,15})/);
            if (m) R.phone = m[1];
        }
        // Website — qualquer link externo que não seja redes sociais ou Google
        if (!R.website) {
            if (href.startsWith('http') &&
                !href.includes('google') && !href.includes('goo.gl') &&
                !href.includes('instagram.com') && !href.includes('facebook.com') &&
                !href.includes('youtube.com') && !href.includes('twitter.com') &&
                !href.includes('x.com') && !href.includes('linkedin.com') &&
                !href.includes('wa.me') && !href.includes('whatsapp.com') &&
                !href.includes('tiktok.com')) {
                R.website = href;
            }
        }
    }

    // Segundo: texto visível (URLs escritas como texto) — captura handles no body
    // Isso é especialmente útil para iframes e seções "Resultados da Web"
    const bodyText = detailRoot.innerText || '';
    if (!R.instagram) {
        // Handle @usuario mencionado próximo a "Instagram"
        const igM = bodyText.match(/instagram[^\n]{0,50}@([A-Za-z0-9._]{2,50})/i) ||
                    bodyText.match(/@([A-Za-z0-9._]{2,50})[^\n]{0,30}instagram/i) ||
                    bodyText.match(/instagram\.com\/([A-Za-z0-9._]{2,50})/i);
        if (igM) {
            const handle = igM[1].replace(/[^A-Za-z0-9._]/g, '');
            if (handle && !bad.has(handle.toLowerCase())) R.instagram = '@' + handle;
        }
    }

    // ── Facebook/LinkedIn/YouTube via "Resultados da Web" sem <a href> real ──
    // O Google às vezes mostra o resultado como breadcrumb em texto puro:
    // "https://www.facebook.com › tyagobarbieri" (sem link clicável real,
    // o <a> que envolve não tem href utilizável). Capturamos esse padrão
    // "dominio.com › slug" do texto visível.
    if (!R.facebook) {
        const fbM = bodyText.match(/facebook\.com\s*[›\/]\s*([A-Za-z0-9._\-]{2,80})/i);
        if (fbM && !bad.has(fbM[1].toLowerCase())) {
            R.facebook = `https://www.facebook.com/${fbM[1].replace(/\s.*$/, '')}`;
        }
    }
    if (!R.linkedin) {
        const liM = bodyText.match(/linkedin\.com\s*[›\/]\s*(?:company|in)\s*[›\/]\s*([A-Za-z0-9._\-]{2,80})/i);
        if (liM && !bad.has(liM[1].toLowerCase())) {
            R.linkedin = `https://www.linkedin.com/company/${liM[1].replace(/\s.*$/, '')}`;
        }
    }
    if (!R.youtube) {
        const ytM = bodyText.match(/youtube\.com\s*[›\/]\s*(?:channel|c|@)?\s*[›\/]?\s*([A-Za-z0-9._\-]{2,80})/i);
        if (ytM && !bad.has(ytM[1].toLowerCase())) {
            R.youtube = `https://www.youtube.com/${ytM[1].replace(/\s.*$/, '')}`;
        }
    }

    // ── Telefone/Endereço via Io6YTe e data-item-id (Maps 2024+) ───────────
    if (!R.phone) {
        for (const el of document.querySelectorAll(
            'button[data-item-id*="phone"], button[aria-label*="Copiar número"], div.Io6YTe'
        )) {
            const did = el.getAttribute('data-item-id') || '';
            const telM = did.match(/tel:([^;]+)/i);
            if (telM) { R.phone = decodeURIComponent(telM[1]); break; }
            const t = (el.getAttribute('aria-label') || el.textContent || '').trim();
            const pm = t.match(/\(?\d{2}\)?\s?(?:9\s?\d{4}|\d{4})[-\s]?\d{4}/);
            if (pm) { R.phone = pm[0]; break; }
        }
    }
    if (!R.address) {
        for (const el of document.querySelectorAll(
            'button[data-item-id*="address"], button[aria-label*="Endereço"], div.Io6YTe'
        )) {
            const lbl = (el.getAttribute('aria-label') || '').replace(/endereço:?/i,'').trim();
            if (lbl.length > 10 && /rua|av|avenida|alameda|travessa|estrada|praça|rod/i.test(lbl)) {
                R.address = lbl; break;
            }
            const t = el.textContent.trim();
            if (/^(Rua|Av|Avenida|Alameda|Travessa|Estrada|Praça|Rod)/i.test(t) && t.length > 12) {
                R.address = t; break;
            }
        }
    }

    // ── Telefone via botão "Ligar" (href tel:) ──────────────────────────────
    if (!R.phone) {
        const telLink = document.querySelector('a[href^="tel:"]');
        if (telLink) {
            R.phone = decodeURIComponent(telLink.getAttribute('href').replace('tel:','').trim());
        }
    }

    // ── WhatsApp direto (botão wa.me na ficha) ────────────────────────────────
    const waLink = document.querySelector('a[href*="wa.me/"], a[href*="api.whatsapp.com/send"]');
    if (waLink) {
        const waHref = waLink.getAttribute('href') || '';
        const waM = waHref.match(/(?:wa\.me\/|phone=)(\d{10,15})/);
        if (waM) R.whatsapp_link = waM[1];
    }

    // ── TikTok ────────────────────────────────────────────────────────────────
    if (!R.tiktok) {
        for (const a of document.querySelectorAll('a[href*="tiktok.com"]')) {
            const m = a.href.match(/tiktok\.com\/@([A-Za-z0-9._]{2,50})/);
            if (m && !bad.has(m[1].toLowerCase())) { R.tiktok = '@' + m[1]; break; }
        }
    }

    // ── Faixa de preço ($, $$, $$$, $$$$) ────────────────────────────────────
    for (const el of document.querySelectorAll('[aria-label]')) {
        const lbl = el.getAttribute('aria-label') || '';
        const pm = lbl.match(/Faixa\s+de\s+pre[cç]o[:\s]+(.{1,20})/i) ||
                   lbl.match(/Price\s+range[:\s]+(.{1,20})/i) ||
                   lbl.match(/^([$€£]{1,4})$/);
        if (pm) { R.price_range = pm[1].trim(); break; }
    }
    // Fallback: texto "$$$" solto no painel
    if (!R.price_range) {
        const priceEl = document.querySelector('span.mgr77e') ||
                        document.querySelector('span[aria-label*="preço"]');
        if (priceEl) R.price_range = priceEl.textContent.trim().slice(0, 10);
    }

    // ── Plus Code ─────────────────────────────────────────────────────────────
    // O Plus Code aparece em: aria-label, data-item-id, ou como texto puro no painel
    for (const el of document.querySelectorAll('[aria-label]')) {
        const lbl = el.getAttribute('aria-label') || '';
        // Formato no aria-label: "Plus Code: Q5QX+R5" ou "Q5QX+R5 Jardim Botânico"
        const pcm = lbl.match(/Plus\s+Code[:\s]+([A-Z0-9]{4,6}\+[A-Z0-9]{2,3})/i) ||
                    lbl.match(/\b([A-Z0-9]{4,6}\+[A-Z0-9]{2,3})\b/);
        if (pcm) { R.plus_code = decodeURIComponent(pcm[1]); break; }
    }
    if (!R.plus_code) {
        // data-item-id pode conter o plus code codificado
        for (const el of document.querySelectorAll('[data-item-id]')) {
            const did = el.getAttribute('data-item-id') || '';
            const pcm = did.match(/plus_code:([A-Z0-9%+]{6,})/i);
            if (pcm) { R.plus_code = decodeURIComponent(pcm[1]); break; }
        }
    }
    if (!R.plus_code) {
        // Texto puro no painel: "Q5QX+R5 Jardim Botânico, Ribeirão Preto"
        const allText = document.body ? document.body.innerText : '';
        // Plus code: 4-6 chars alfanum + '+' + 2-3 chars — formato OLC padrão
        const plm = allText.match(/\b([A-Z0-9]{4,6}\+[A-Z0-9]{2,3})\b/);
        if (plm) R.plus_code = plm[1];
    }

    // ── Amenidades / Atributos do lugar ──────────────────────────────────────
    // O Google Maps exibe atributos em várias estruturas dependendo da versão/categoria.
    // Coletamos de todas as fontes conhecidas e deduplicamos.
    const amenitySelectors = [
        // Containers de atributos v2024 (acessibilidade, pagamentos, etc.)
        'div.iP2t7d span',
        'div.E0DTEd span',
        'li.hpLkke span',
        'div.sSHqwe span',
        'div.lX8Tbe span',
        'div.ekb8yd span',
        // aria-label com atributos comuns
        '[aria-label*="Aceita"]',
        '[aria-label*="Wi-Fi"]',
        '[aria-label*="Acessív"]',
        '[aria-label*="Estacionamento"]',
        '[aria-label*="Pagamento"]',
        '[aria-label*="Refeição"]',
        '[aria-label*="Serviço"]',
        '[aria-label*="Planejamento"]',
        '[aria-label*="Crianças"]',
        '[aria-label*="Animal"]',
        '[aria-label*="LGBTQ"]',
        // Seção "Sobre o lugar" / informações adicionais
        '[data-item-id*="attribute"] span',
        '[data-item-id*="amenity"] span',
        // Estrutura com ícone + texto: div.Io6YTe
        'div.Io6YTe',
        // Lista de recursos (v2023)
        'ul.ZjVtHb li',
    ];
    const seenAmenities = new Set();
    for (const sel of amenitySelectors) {
        for (const el of document.querySelectorAll(sel)) {
            // Prioriza aria-label; cai para textContent
            const t = (el.getAttribute('aria-label') || el.textContent || '').trim()
                       .replace(/\s+/g, ' ');
            if (t && t.length > 3 && t.length < 120 && !seenAmenities.has(t)) {
                // Filtra textos que são claramente botões de ação ou navegação
                const skip = /^(Rotas|Salvar|Compartilhar|Avaliar|Ligar|Enviar|Sugerir|Adicionar|Ordenar|Pesquisar|Avaliações|Sobre|Visão geral|Serviços|Produtos|Ver|Abrir|Fechar|Mais|Menos|Editar|Denunciar)$/i.test(t);
                if (!skip) {
                    seenAmenities.add(t);
                    R.amenities.push(t);
                }
            }
            if (R.amenities.length >= 50) break;
        }
        if (R.amenities.length >= 50) break;
    }

    // ── Número total de fotos ─────────────────────────────────────────────────
    for (const el of document.querySelectorAll('[aria-label]')) {
        const lbl = el.getAttribute('aria-label') || '';
        const pm = lbl.match(/([\d.,]+)\s*(?:fotos?|photos?)/i);
        if (pm) {
            R.total_photos = parseInt(pm[1].replace(/[^\d]/g,''), 10) || null;
            break;
        }
    }

    // ── Foto principal da galeria (fallback melhorado) ────────────────────────
    if (!R.og_image) {
        // Tenta a foto de capa do Maps (button.aoRNLd > img)
        const heroImg = document.querySelector('button.aoRNLd img') ||
                        document.querySelector('.RZ66Rb img') ||
                        document.querySelector('img.t2cCgb') ||
                        document.querySelector('div.lu_map_section img');
        if (heroImg && heroImg.src && !heroImg.src.startsWith('data:')) {
            R.og_image = heroImg.src;
        }
    }

    // ── Link compartilhável ───────────────────────────────────────────────────
    const shareInput = document.querySelector(
        'input[value*="share.google"], input[value*="maps.app.goo.gl"], input[value*="goo.gl/maps"]'
    );
    if (shareInput) R.share_url = shareInput.value;

    // ── Status aberto/fechado ─────────────────────────────────────────────────
    // NOTA: bodyText já foi declarado com const acima — reutilizamos a variável
    if (/\baberto\b/i.test(bodyText)) R.hours.aberto_agora = true;
    else if (/\bfechado\b/i.test(bodyText)) R.hours.aberto_agora = false;

    const statusM = bodyText.match(
        /(Aberto\s*(?:24\s*horas)?|Fechado\s*(?:agora)?|Abre\s*às\s*\d{1,2}:\d{2}|Fecha\s*às\s*\d{1,2}:\d{2})/i
    );
    if (statusM) R.hours.status_atual = statusM[1].trim();

    return R;
};