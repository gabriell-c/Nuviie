/* global NuviieMaps */
window.NuviieMaps = window.NuviieMaps || {};

NuviieMaps._webResultsCtx = null;

NuviieMaps.normalizeSearchToken = (s) => (s || '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, ' ')
    .trim();

NuviieMaps.CONTACT_BAD_DOMAINS = /google|goo\.gl|gstatic|schema\.org|googleusercontent|googleapis/i;

NuviieMaps.isLikelyRatingCategory = (text) => {
    if (!text) return true;
    const t = text.trim();
    if (/^\d+[.,]\d+(\(\d+\))?$/.test(t)) return true;
    if (/estrelas?|stars?|avalia/i.test(t)) return true;
    return false;
};

NuviieMaps.normalizeDomainText = (text) => {
    const raw = (text || '').trim();
    if (!raw) return '';
    if (/^https?:\/\//i.test(raw)) return raw.replace(/[?#].*/, '');
    const m = raw.match(/\b((?:[a-z0-9-]+\.)+[a-z]{2,}(?:\.[a-z]{2,})?)\b/i);
    if (!m) return '';
    const domain = m[1].toLowerCase();
    if (NuviieMaps.CONTACT_BAD_DOMAINS.test(domain)) return '';
    if (/^(instagram|facebook|youtube|twitter|linkedin|tiktok|wa)\./i.test(domain)) return '';
    if (/^(maps|goo)\./i.test(domain)) return '';
    return `https://${domain.replace(/^www\./i, '')}`;
};

NuviieMaps.mergeExtractData = (primary, secondary) => {
    const out = { ...(primary || {}) };
    for (const [k, v] of Object.entries(secondary || {})) {
        if (v != null && v !== '' && !out[k]) out[k] = v;
    }
    return out;
};

NuviieMaps.getWebResultsContext = (placeName) => {
    const detailRoot = document.querySelector('[role="main"]') || document.body;
    const nameNorm = NuviieMaps.normalizeSearchToken(placeName);
    const nameTokens = nameNorm.split(' ').filter((w) => w.length >= 3);

    const frames = [];
    const seen = new Set();
    for (const root of [detailRoot, document.body]) {
        root.querySelectorAll('iframe.rvN3ke, iframe[src*="/search"]').forEach((f) => {
            if (!seen.has(f)) {
                seen.add(f);
                frames.push(f);
            }
        });
    }

    const tryFrame = (frame, requireNameMatch) => {
        try {
            if (requireNameMatch && nameTokens.length) {
                let frameQuery = '';
                try {
                    frameQuery = NuviieMaps.normalizeSearchToken(decodeURIComponent(frame.getAttribute('src') || ''));
                } catch (e) {
                    frameQuery = NuviieMaps.normalizeSearchToken(frame.getAttribute('src') || '');
                }
                if (!nameTokens.some((t) => frameQuery.includes(t))) return null;
            }
            const fdoc = frame.contentDocument || frame.contentWindow?.document;
            if (fdoc) return { frame, fdoc, fwin: frame.contentWindow, nameTokens };
        } catch (e) { /* iframe blocked */ }
        return null;
    };

    const detailFrames = frames.filter((f) => detailRoot === document.body || detailRoot.contains(f));

    for (const frame of detailFrames) {
        const ctx = tryFrame(frame, true);
        if (ctx) return ctx;
    }
    for (const frame of detailFrames) {
        const ctx = tryFrame(frame, false);
        if (ctx) return ctx;
    }
    return null;
};

NuviieMaps._iframeHasRealLinks = (ctx) => {
    if (!ctx?.fdoc) return false;
    const doc = ctx.fdoc;
    const socialLink = doc.querySelector(
        'a[href*="instagram.com"], a[href*="facebook.com"], a[href*="linkedin.com"], ' +
        'a[href*="youtube.com"], a[href*="twitter.com"], a[href*="x.com"]'
    );
    if (socialLink?.href) return true;
    const cards = doc.querySelectorAll('#gsr .V2ynS, .RMrS6d, .CIdPsb');
    for (const card of cards) {
        const text = (card.textContent || '').trim();
        if (text.length > 8 && !/CiOaN|skeleton|loading/i.test(text)) return true;
    }
    return false;
};

NuviieMaps.waitForWebResultsIframe = async (placeName, maxMs = 5000, intervalMs = 150) => {
    const deadline = Date.now() + maxMs;
    let ctx = null;
    while (Date.now() < deadline) {
        ctx = NuviieMaps.getWebResultsContext(placeName);
        if (ctx && NuviieMaps._iframeHasRealLinks(ctx)) {
            NuviieMaps._webResultsCtx = ctx;
            return ctx;
        }
        if (NuviieMaps.hasWebResultsContent && NuviieMaps.hasWebResultsContent()) {
            break;
        }
        await new Promise((r) => setTimeout(r, intervalMs));
    }
    ctx = NuviieMaps.getWebResultsContext(placeName);
    if (ctx && NuviieMaps._iframeHasRealLinks(ctx)) {
        NuviieMaps._webResultsCtx = ctx;
        return ctx;
    }
    NuviieMaps._webResultsCtx = null;
    return null;
};

NuviieMaps.collectWjd = (fwin, fdoc) => {
    const out = {};
    const fromWin = fwin?.W_jd;
    if (fromWin && typeof fromWin === 'object') {
        Object.assign(out, fromWin);
    }
    if (fdoc) {
        const html = fdoc.documentElement?.innerHTML || '';
        // Pares ["https://...", 0] do script inline W_jd
        let i = 0;
        for (const m of html.matchAll(/\["(https:\/\/[^"]+)",\s*\d+\]/g)) {
            out[`_inline${i++}`] = [m[1], 0];
        }
    }
    return out;
};

NuviieMaps.detectCardPlatform = (card) => {
    const faviconAlt = (card.querySelector('img.l5D6lb')?.getAttribute('alt') || '').toLowerCase();
    const cidText = (card.querySelector('.CIdPsb')?.textContent || '').toLowerCase();
    const src = `${faviconAlt} ${cidText}`;
    if (/facebook\.com/.test(src)) return 'facebook';
    if (/instagram\.com/.test(src)) return 'instagram';
    if (/linkedin\.com/.test(src)) return 'linkedin';
    if (/youtube\.com/.test(src)) return 'youtube';
    if (/twitter\.com|x\.com/.test(src)) return 'twitter';
    if (/tiktok\.com/.test(src)) return 'tiktok';
    return 'website';
};

NuviieMaps.parseSearchResultCard = (R, card, bad) => {
    const cardLink = card.querySelector('a[href]');
    if (cardLink?.href) NuviieMaps.applySocialUrl(R, cardLink.href, bad);

    const cidPsb = card.querySelector('.CIdPsb');
    const faviconAlt = card.querySelector('img.l5D6lb')?.getAttribute('alt') || '';
    const urlText = (cidPsb?.textContent || faviconAlt || card.textContent || '').trim();
    const platform = NuviieMaps.detectCardPlatform(card);
    let url = NuviieMaps.breadcrumbToUrl(urlText);

    if (url) NuviieMaps.applySocialUrl(R, url, bad);

    // Facebook/Instagram às vezes só aparecem no breadcrumb truncado — força pelo favicon
    if (platform === 'facebook' && !R.facebook && urlText) {
        const slugM = urlText.match(/facebook\.com\s*[›>\s]+\s*(.+)/i);
        if (slugM) {
            const slug = slugM[1].replace(/[\s.…]+$/g, '').trim();
            if (slug && !bad.has(slug.toLowerCase().replace(/^p\//, ''))) {
                R.facebook = slug.startsWith('p/') || slug.startsWith('profile.php')
                    ? `https://www.facebook.com/${slug}`
                    : `https://www.facebook.com/${slug}`;
            }
        }
    }
    if (platform === 'instagram' && !R.instagram && urlText) {
        const igM = urlText.match(/instagram\.com\s*[›>\s]+\s*@?([A-Za-z0-9._]+)/i);
        if (igM && !bad.has(igM[1].toLowerCase())) R.instagram = '@' + igM[1];
    }

    const snippet = (card.querySelector('.GhV79b')?.textContent || '').trim();
    if (snippet && !R.address) {
        const addrM = snippet.match(/(?:Avenida|Av\.?|Rua|Alameda|Travessa|Estrada|Pra[cç]a|Rod\.?)[^;,\n]{8,200}(?:,\s*[^,\n]{2,40}){0,4}/i);
        if (addrM) R.address = addrM[0].replace(/\s+/g, ' ').trim();
    }
    if (snippet && !R.bio && snippet.length > 30 && !/not yet rated|avalia|reviews?\)/i.test(snippet)) {
        R.bio = snippet.slice(0, 800);
    }
};

NuviieMaps.resolveGoogleRedirect = (href) => {
    let url = (href || '').trim();
    if (!url) return '';
    const redirectM = url.match(/[?&]q=([^&]+)/);
    if (redirectM && /\/url\?/.test(url)) {
        try { url = decodeURIComponent(redirectM[1]); } catch (e) { /* ignore */ }
    }
    return url;
};

NuviieMaps.breadcrumbToUrl = (text) => {
    const raw = (text || '').trim();
    if (!raw) return '';
    if (/^https?:\/\//i.test(raw)) return raw.split(/\s*[›>]\s*/)[0].trim();
    const m = raw.match(/^(https?:\/\/[^\s›>]+)(?:\s*[›>]\s*(.+))?/i);
    if (!m) return '';
    const base = m[1].replace(/\/$/, '');
    const path = (m[2] || '').trim().replace(/\s.*/,'');
    if (!path) return base + '/';
    if (/^www\./i.test(path) || path.includes('.')) return `https://${path}`;
    if (/instagram\.com/i.test(base)) return `${base}/${path.replace(/^@/, '')}/`;
    if (/facebook\.com/i.test(base)) return `${base}/${path}/`;
    if (/linkedin\.com/i.test(base)) {
        if (/^(in|company)\//i.test(path)) return `${base}/${path}/`;
        return `${base}/company/${path}/`;
    }
    if (/youtube\.com/i.test(base)) return `${base}/${path}/`;
    return `${base}/${path}/`;
};

NuviieMaps.applySocialUrl = (R, href, bad) => {
    let url = NuviieMaps.resolveGoogleRedirect(href);
    if (!url || url.startsWith('javascript:')) return;

    if (!R.instagram) {
        const m = url.match(/instagram\.com\/([A-Za-z0-9._]{2,50})/);
        if (m && !bad.has(m[1].toLowerCase())) R.instagram = '@' + m[1].replace(/\/$/, '');
    }
    if (!R.facebook) {
        const m = url.match(/facebook\.com\/(?:p\/)?([A-Za-z0-9._\-]{2,120})/);
        if (m && !bad.has(m[1].toLowerCase())) R.facebook = url.replace(/[?#].*/, '');
    }
    if (!R.youtube) {
        const m = url.match(/youtube\.com\/(?:channel\/|c\/|@)([A-Za-z0-9._\-]{2,80})/);
        if (m && !bad.has(m[1].toLowerCase())) R.youtube = url.replace(/[?#].*/, '');
    }
    if (!R.twitter) {
        const m = url.match(/(?:twitter|x)\.com\/([A-Za-z0-9._]{2,50})/);
        if (m && !bad.has(m[1].toLowerCase())) R.twitter = url.replace(/[?#].*/, '');
    }
    if (!R.linkedin) {
        const m = url.match(/linkedin\.com\/(in|company)\/([A-Za-z0-9._\-]{2,80})/);
        if (m && !bad.has(m[2].toLowerCase())) R.linkedin = url.replace(/[?#].*/, '');
    }
    if (!R.tiktok) {
        const m = url.match(/tiktok\.com\/@([A-Za-z0-9._]{2,50})/);
        if (m && !bad.has(m[1].toLowerCase())) R.tiktok = '@' + m[1];
    }
    if (!R.phone) {
        const m = url.match(/wa\.me\/(\d{10,15})/);
        if (m) R.phone = m[1];
    }
    if (!R.website) {
        if (url.startsWith('http') &&
            !url.includes('google') && !url.includes('goo.gl') &&
            !url.includes('instagram.com') && !url.includes('facebook.com') &&
            !url.includes('youtube.com') && !url.includes('twitter.com') &&
            !url.includes('x.com') && !url.includes('linkedin.com') &&
            !url.includes('wa.me') && !url.includes('whatsapp.com') &&
            !url.includes('tiktok.com')) {
            R.website = url.replace(/[?#].*/, '');
        }
    }
};

NuviieMaps.extractFromWebResults = (R, ctx, bad) => {
    if (!ctx?.fdoc) return { links: [], doc: null };
    const { fdoc, fwin } = ctx;

    // 1) W_jd — mapa explícito de URLs (prioridade)
    const wjd = NuviieMaps.collectWjd(fwin, fdoc);
    for (const val of Object.values(wjd)) {
        const url = Array.isArray(val) ? val[0] : val;
        if (url) NuviieMaps.applySocialUrl(R, url, bad);
    }

    // 2) Cards "Resultados da Web" — SEMPRE parsear (W_jd pode estar incompleto)
    for (const card of fdoc.querySelectorAll(
        '#gsr .V2ynS, .RMrS6d, div.V2ynS, #gsr a[data-hveid], [data-hveid].V2ynS'
    )) {
        NuviieMaps.parseSearchResultCard(R, card, bad);
    }

    // 3) Links <a href> dentro do iframe (redirects do Google)
    const links = [...fdoc.querySelectorAll('a[href]')];
    for (const a of links) {
        NuviieMaps.applySocialUrl(R, a.href, bad);
    }

    // 4) Texto visível do iframe
    NuviieMaps.applySocialFromText(R, fdoc.body?.innerText || '', bad);

    return { links, doc: fdoc };
};

NuviieMaps.applySocialFromText = (R, bodyText, bad) => {
    if (!bodyText) return;
    if (!R.instagram) {
        const igM = bodyText.match(/instagram[^\n]{0,50}@([A-Za-z0-9._]{2,50})/i) ||
                    bodyText.match(/@([A-Za-z0-9._]{2,50})[^\n]{0,30}instagram/i) ||
                    bodyText.match(/instagram\.com\s*[›\/>\s]+\s*([A-Za-z0-9._]{2,50})/i) ||
                    bodyText.match(/instagram\.com\/([A-Za-z0-9._]{2,50})/i);
        if (igM) {
            const handle = igM[1].replace(/[^A-Za-z0-9._]/g, '');
            if (handle && !bad.has(handle.toLowerCase())) R.instagram = '@' + handle;
        }
    }
    if (!R.facebook) {
        const fbM = bodyText.match(/facebook\.com\s*[›\/>\s]+\s*(p\/[A-Za-z0-9._\-]+|Dr-[A-Za-z0-9._\-]+|[A-Za-z0-9._\-]{2,120})/i);
        if (fbM) {
            const slug = fbM[1].replace(/[\s.…]+$/g, '').trim();
            if (slug && !bad.has(slug.toLowerCase().replace(/^p\//, ''))) {
                R.facebook = `https://www.facebook.com/${slug}`;
            }
        }
    }
    if (!R.linkedin) {
        const liM = bodyText.match(/linkedin\.com\s*[›\/>\s]+\s*(in|company)\s*[›\/>\s]+\s*([A-Za-z0-9._\-]{2,80})/i);
        if (liM && !bad.has(liM[2].toLowerCase())) {
            R.linkedin = `https://www.linkedin.com/${liM[1].toLowerCase()}/${liM[2].replace(/\s.*$/, '')}`;
        }
    }
    if (!R.youtube) {
        const ytM = bodyText.match(/youtube\.com\s*[›\/>\s]+\s*(?:channel|c|@)?\s*[›\/>\s]?\s*([A-Za-z0-9._\-@]{2,80})/i);
        if (ytM && !bad.has(ytM[1].toLowerCase())) {
            R.youtube = `https://www.youtube.com/${ytM[1].replace(/\s.*$/, '')}`;
        }
    }
    if (!R.tiktok) {
        const ttM = bodyText.match(/tiktok\.com\s*[›\/>\s]+\s*@?([A-Za-z0-9._]{2,50})/i);
        if (ttM && !bad.has(ttM[1].toLowerCase())) R.tiktok = '@' + ttM[1].replace(/\s.*$/, '');
    }
};

NuviieMaps.extractWebResultsFromMainPanel = (R, bad) => {
    const detailRoot = document.querySelector('[role="main"]') || document.body;
    const headings = ['Resultados da Web', 'Web results', 'Resultados web'];
    let section = null;

    for (const el of detailRoot.querySelectorAll('h2, div, span, button')) {
        const t = (el.textContent || '').trim();
        if (headings.some((h) => t === h || t.startsWith(h))) {
            section = el.closest('div[jsaction]') || el.parentElement?.parentElement || el.parentElement;
            break;
        }
    }

    const searchRoot = section || detailRoot;
    for (const card of searchRoot.querySelectorAll(
        '#gsr .V2ynS, .RMrS6d, div.V2ynS, [data-hveid], a[href*="instagram.com"], a[href*="facebook.com"]'
    )) {
        if (card.matches('a[href]')) {
            NuviieMaps.applySocialUrl(R, card.href, bad);
        } else {
            NuviieMaps.parseSearchResultCard(R, card, bad);
        }
    }
};

NuviieMaps.extractContactFields = () => {
    const R = {
        website: null, instagram: null, facebook: null, youtube: null,
        twitter: null, linkedin: null, tiktok: null, phone: null, whatsapp_link: null,
    };
    const bad = new Set(['explore','reel','reels','p','stories','tv','accounts',
                         'tags','share','sharer','intent','home','watch','results',
                         'search','jobs','feed','ads','about','legal','privacy',
                         'support','notifications','explore','highlights']);
    const detailRoot = document.querySelector('[role="main"]') || document.body;

    for (const sel of [
        'a[data-item-id="authority"]',
        'button[data-item-id="authority"]',
        'a[data-item-id*="authority"]',
        'a[aria-label*="Website"]',
        'a[aria-label*="website"]',
        'a[aria-label*="site"]',
        'a[aria-label*="Site"]',
    ]) {
        detailRoot.querySelectorAll(sel).forEach((el) => {
            const href = el.href || el.getAttribute('href') || el.getAttribute('data-href') || '';
            if (href) NuviieMaps.applySocialUrl(R, href, bad);
        });
    }

    detailRoot.querySelectorAll('[aria-label]').forEach((el) => {
        const lbl = el.getAttribute('aria-label') || '';
        const siteM = lbl.match(/(?:website|site)[:\s]+(.+)/i);
        if (siteM) {
            const url = NuviieMaps.normalizeDomainText(siteM[1]) || siteM[1].trim();
            if (url) NuviieMaps.applySocialUrl(R, url, bad);
        }
    });

    detailRoot.querySelectorAll('div.Io6YTe, div.AeaXub').forEach((el) => {
        const t = el.textContent.trim();
        const parent = el.closest('a[href]');
        if (parent?.href) NuviieMaps.applySocialUrl(R, parent.href, bad);
        const domainUrl = NuviieMaps.normalizeDomainText(t);
        if (domainUrl) NuviieMaps.applySocialUrl(R, domainUrl, bad);
        else NuviieMaps.applySocialFromText(R, t, bad);
    });

    detailRoot.querySelectorAll(
        'a[href*="instagram.com"], a[href*="facebook.com"], a[href*="wa.me"], ' +
        'a[href*="linkedin.com"], a[href*="youtube.com"], a[href*="twitter.com"], a[href*="x.com"]'
    ).forEach((a) => {
        NuviieMaps.applySocialUrl(R, a.href, bad);
    });

    return R;
};

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
        if (catText && !notCat.has(catText) && catText.length > 2 && catText.length < 80
            && !NuviieMaps.isLikelyRatingCategory(catText)) {
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

    NuviieMaps.extractWebResultsFromMainPanel(R, bad);

    const contactFields = NuviieMaps.extractContactFields();
    Object.entries(contactFields).forEach(([k, v]) => {
        if (v && !R[k]) R[k] = v;
    });

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
        const ctx = NuviieMaps._webResultsCtx || NuviieMaps.getWebResultsContext(R.name);
        if (ctx) {
            const wr = NuviieMaps.extractFromWebResults(R, ctx, bad);
            webResultsLinks = wr.links;
            webResultsDoc = wr.doc;
        }
    } catch (e) {}
    NuviieMaps._webResultsCtx = null;

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

    // Links diretos (painel principal + iframe "Resultados da Web")
    for (const a of [...detailRoot.querySelectorAll('a[href]'), ...webResultsLinks]) {
        NuviieMaps.applySocialUrl(R, a.href, bad);
    }

    // Texto visível — painel principal + iframe
    const bodyText = detailRoot.innerText || '';
    const webText = webResultsDoc?.body?.innerText || '';
    NuviieMaps.applySocialFromText(R, bodyText, bad);
    if (webText && webText !== bodyText) {
        NuviieMaps.applySocialFromText(R, webText, bad);
    }

    // ── Telefone/Endereço via Io6YTe e data-item-id (Maps 2024+) ───────────
    if (!R.phone) {
        for (const el of detailRoot.querySelectorAll(
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
        for (const el of detailRoot.querySelectorAll(
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
        const telLink = detailRoot.querySelector('a[href^="tel:"]');
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