/* global NuviieMaps */
window.NuviieMaps = window.NuviieMaps || {};

NuviieMaps.SCROLL_CONTAINER_SELECTORS = [
  '.e07Vkf.kA9KIf.dS8AEf',
  '.k7jAl.lJ3Kh',
  'div[role="main"]',
  '.DxyBCb',
  '.bJzME',
  '.siAUzd',
  '[jsaction*="scrollable.focus"]',
];

NuviieMaps.getDetailScrollContainer = () => {
  const panel = NuviieMaps.getDetailPanelRoot();
  for (const sel of NuviieMaps.SCROLL_CONTAINER_SELECTORS) {
    const el = panel.closest('.bJzME')?.querySelector(sel) || document.querySelector(sel);
    if (el && el.scrollHeight > el.clientHeight + 20) return el;
  }
  for (const sel of NuviieMaps.SCROLL_CONTAINER_SELECTORS) {
    const el = panel.closest('.bJzME')?.querySelector(sel) || document.querySelector(sel);
    if (el) return el;
  }
  return null;
};

NuviieMaps.setScrollTop = (scrollTop) => {
  const container = NuviieMaps.getDetailScrollContainer();
  if (container) {
    container.scrollTop = scrollTop;
    return container;
  }
  window.scrollTo(0, scrollTop);
  return null;
};

NuviieMaps.waitForCondition = async (fn, maxMs = 5000, intervalMs = 100) => {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    try {
      const result = fn();
      if (result) return result;
    } catch { /* ignore */ }
    await NuviieMaps.sleep(intervalMs);
  }
  return null;
};

NuviieMaps.getDetailH1Text = () => {
  const root = NuviieMaps.getDetailPanelRoot();
  const h1 = root.querySelector('h1.DUwDvf')
    || root.querySelector('h1')
    || document.querySelector('h1.DUwDvf')
    || document.querySelector('h1');
  return h1 ? h1.textContent.trim() : '';
};

NuviieMaps.placeNamesMatch = (a, b, minTokens = 2) => {
  if (!a || !b) return false;
  const norm = (s) => (s || '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, ' ')
    .trim();
  const tokensA = norm(a).split(/\s+/).filter((w) => w.length >= 3);
  const tokensB = norm(b).split(/\s+/).filter((w) => w.length >= 3);
  if (!tokensA.length || !tokensB.length) {
    return norm(a) === norm(b);
  }
  const matches = tokensA.filter((t) => tokensB.some((u) => u.includes(t) || t.includes(u)));
  const need = Math.min(minTokens, tokensA.length, tokensB.length);
  return matches.length >= need;
};

NuviieMaps.waitForPlaceReady = async (linkInfo, maxMs = 8000) => {
  const expectedFromUrl = NuviieMaps.nameFromUrl(linkInfo.href || linkInfo.base || '');
  const expectedBase = linkInfo.base || NuviieMaps.basePlaceUrl(linkInfo.href || '');
  const urlAlreadyMatches = expectedBase && NuviieMaps.basePlaceUrl(window.location.href) === expectedBase;
  const timeout = urlAlreadyMatches ? Math.min(maxMs, 5000) : maxMs;

  const result = await NuviieMaps.waitForCondition(() => {
    const currentBase = NuviieMaps.basePlaceUrl(window.location.href);
    const urlMatches = expectedBase && currentBase === expectedBase;
    const h1 = NuviieMaps.getDetailH1Text();
    const h1Valid = NuviieMaps.isValidPlaceName(h1) && h1.toLowerCase() !== 'resultados';

    if (expectedFromUrl && h1Valid && NuviieMaps.placeNamesMatch(h1, expectedFromUrl)) {
      return { name: h1, fromUrl: expectedFromUrl, urlMatched: urlMatches, warnings: [] };
    }
    if (urlMatches && h1Valid) {
      return { name: h1, fromUrl: expectedFromUrl || h1, urlMatched: true, warnings: [] };
    }
    return null;
  }, timeout, 80);

  if (result) return result;

  const h1 = NuviieMaps.getDetailH1Text();
  const warnings = [];
  if (expectedFromUrl) {
    if (h1 && NuviieMaps.isValidPlaceName(h1) && !NuviieMaps.placeNamesMatch(h1, expectedFromUrl)) {
      warnings.push('h1_url_mismatch');
    }
    return {
      name: expectedFromUrl,
      fromUrl: expectedFromUrl,
      urlMatched: false,
      warnings,
    };
  }
  if (h1 && NuviieMaps.isValidPlaceName(h1)) {
    return { name: h1, fromUrl: h1, urlMatched: false, warnings };
  }
  return { name: '', fromUrl: '', urlMatched: false, warnings: ['panel_not_ready'] };
};

NuviieMaps.isWebResultsFullyLoaded = () => {
  const section = NuviieMaps.getWebResultsSection();
  if (!section) return false;

  if (section.querySelector(
    'a[href*="facebook.com"], a[href*="linkedin.com"], a[href*="instagram.com"], a[href*="youtube.com"]'
  )) {
    return true;
  }

  const cards = section.querySelectorAll('.lXJj5c, .OBAKjf, .RMrS6d, .V2ynS, .CIdPsb, .ATb88b');
  for (const card of cards) {
    const text = (card.textContent || '').trim();
    if (text.length > 15 && !card.querySelector('.CiOaN')) return true;
  }
  return false;
};

NuviieMaps.scrollUntilWebResultsComplete = async (maxMs = 5500) => {
  const deadline = Date.now() + maxMs;

  while (Date.now() < deadline) {
    if (NuviieMaps.isWebResultsFullyLoaded()) return true;

    const container = NuviieMaps.getDetailScrollContainer();
    if (container) {
      const maxScroll = container.scrollHeight - container.clientHeight;
      if (container.scrollTop >= maxScroll - 40) {
        await NuviieMaps.sleep(200);
        if (NuviieMaps.isWebResultsFullyLoaded()) return true;
        break;
      }
      container.scrollTop = Math.min(
        container.scrollTop + Math.max(320, Math.floor(container.clientHeight * 0.9)),
        maxScroll,
      );
    } else {
      NuviieMaps.setScrollTop(999999);
    }
    await NuviieMaps.sleep(100);
  }

  const section = NuviieMaps.getWebResultsSection();
  if (section) {
    section.scrollIntoView({ block: 'end', behavior: 'instant' });
    await NuviieMaps.sleep(250);
  }
  NuviieMaps.setScrollTop(999999);
  await NuviieMaps.sleep(200);
  return NuviieMaps.isWebResultsFullyLoaded();
};

NuviieMaps.scrollUntilSection = async (labels, maxMs = 5500) => {
  return NuviieMaps.scrollUntilWebResultsComplete(maxMs);
};

NuviieMaps.scrollPanel = async ({ light = false } = {}) => {
  if (light) {
    for (const stepPx of [300, 900, 99999]) {
      NuviieMaps.setScrollTop(stepPx);
      await NuviieMaps.sleep(180);
    }
    NuviieMaps.setScrollTop(0);
    await NuviieMaps.sleep(150);
    return;
  }
  await NuviieMaps.scrollUntilWebResultsComplete(5000);
  NuviieMaps.setScrollTop(0);
  await NuviieMaps.sleep(200);
};

NuviieMaps.expandHours = async () => {
  const detailRoot = NuviieMaps.getDetailPanelRoot();
  const selectors = [
    'div.OMl5r[jsaction*="openhours"][aria-expanded="false"]',
    'div.OMl5r[aria-expanded="false"]',
    'div[jsaction*="openhours"][aria-expanded="false"]',
  ];
  for (const sel of selectors) {
    const el = detailRoot.querySelector(sel);
    if (el) {
      el.click();
      await NuviieMaps.sleep(250);
      return;
    }
  }
};

NuviieMaps.clickTab = async (labels) => {
  const detailRoot = NuviieMaps.getDetailPanelRoot().closest('.bJzME')
    || document.querySelector('.bJzME')
    || NuviieMaps.getDetailPanelRoot();
  for (const label of labels) {
    for (const tab of detailRoot.querySelectorAll('[role="tab"], button.hh2c6')) {
      const t = (tab.textContent || tab.getAttribute('aria-label') || '').trim();
      if (t === label || t.toLowerCase() === label.toLowerCase() || (tab.getAttribute('aria-label') || '').includes(label)) {
        tab.click();
        await NuviieMaps.sleep(400);
        return true;
      }
    }
  }
  return false;
};

NuviieMaps.goToOverview = async () => {
  await NuviieMaps.clickTab(['Visão geral', 'Visao geral']);
};

NuviieMaps.visitAboutTab = async () => {
  const ok = await NuviieMaps.clickTab(['Sobre']);
  if (!ok) return [];
  await NuviieMaps.scrollPanel({ light: true });
  const amenities = NuviieMaps.extractAboutAmenities();
  await NuviieMaps.goToOverview();
  await NuviieMaps.sleep(300);
  return amenities;
};

NuviieMaps.reviewContainersCount = () => (
  document.querySelectorAll('[data-review-id], div.jftiEf').length
);

// Rola a lista de avaliações até carregar reviews suficientes (lazy-load do Maps).
NuviieMaps.loadReviewsList = async ({ minReviews = 10, maxSteps = 8 } = {}) => {
  let lastCount = -1;
  for (let i = 0; i < maxSteps; i++) {
    const count = NuviieMaps.reviewContainersCount();
    if (count >= minReviews) break;
    if (count === lastCount && count > 0 && i > 1) break; // não carrega mais
    lastCount = count;
    NuviieMaps.setScrollTop(99999);
    await NuviieMaps.sleep(350);
  }
};

NuviieMaps.visitReviewsTab = async ({ fast = false } = {}) => {
  const ok = await NuviieMaps.clickTab(['Avaliações', 'Avaliacoes']);
  if (!ok) {
    // Fallback: tenta extrair o que já estiver visível na ficha.
    await NuviieMaps.loadReviewsList({ minReviews: 5, maxSteps: 4 });
    return NuviieMaps.extractReviews();
  }
  // Espera os primeiros containers de avaliação renderizarem após trocar de aba.
  await NuviieMaps.waitForCondition(() => NuviieMaps.reviewContainersCount() > 0, 4000, 150);
  await NuviieMaps.loadReviewsList({ minReviews: 10, maxSteps: fast ? 6 : 10 });
  if (!fast) {
    NuviieMaps.getDetailPanelRoot().querySelectorAll(
      'button[aria-label*="Ver mais"], button.w8nwRe, button[jsaction*="reviewfulltext"]'
    ).forEach((btn) => {
      try { btn.click(); } catch { /* ignore */ }
    });
    await NuviieMaps.sleep(250);
  }
  const reviews = NuviieMaps.extractReviews();
  NuviieMaps.setScrollTop(0);
  await NuviieMaps.goToOverview();
  await NuviieMaps.sleep(300);
  return reviews;
};

NuviieMaps.scrollToWebResults = async () => {
  await NuviieMaps.scrollUntilWebResultsComplete(4500);
};

NuviieMaps.scrollToTopContact = async () => {
  NuviieMaps.setScrollTop(0);
  await NuviieMaps.sleep(200);
};

NuviieMaps.revealContactButtons = async () => {
  const detailRoot = NuviieMaps.getDetailPanelRoot();
  const selectors = [
    'button[data-item-id*="phone"]',
    'button[aria-label*="Copiar número"]',
    'button[aria-label*="Ligar"]',
    'button[aria-label*="telefone"]',
    'button[aria-label*="Phone"]',
    'button[data-item-id*="address"]',
    'button[aria-label*="Endereço"]',
  ];
  for (const sel of selectors) {
    const btn = detailRoot.querySelector(sel);
    if (btn && btn.offsetParent !== null) {
      try {
        btn.click();
        await NuviieMaps.sleep(150);
      } catch { /* ignore */ }
    }
  }
};

NuviieMaps.waitForStableH1 = async (maxAttempts = 25) => {
  for (let i = 0; i < maxAttempts; i++) {
    const text = NuviieMaps.getDetailH1Text();
    if (NuviieMaps.isValidPlaceName(text) && text.toLowerCase() !== 'resultados') return text;
    await NuviieMaps.sleep(150);
  }
  return NuviieMaps.nameFromUrl(window.location.href) || '';
};

NuviieMaps.clickPlaceLink = async (linkInfo) => {
  if (linkInfo.element && document.contains(linkInfo.element)) {
    linkInfo.element.scrollIntoView({ block: 'center', behavior: 'instant' });
    linkInfo.element.click();
    await NuviieMaps.sleep(450);
    return true;
  }
  const anchor = [...document.querySelectorAll('a[href*="/maps/place/"]')].find(
    (a) => NuviieMaps.basePlaceUrl(a.href) === linkInfo.base
  );
  if (anchor) {
    anchor.scrollIntoView({ block: 'center', behavior: 'instant' });
    anchor.click();
    await NuviieMaps.sleep(450);
    return true;
  }
  return false;
};
