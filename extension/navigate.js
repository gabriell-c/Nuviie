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
  for (const sel of NuviieMaps.SCROLL_CONTAINER_SELECTORS) {
    const el = document.querySelector(sel);
    if (el && el.scrollHeight > el.clientHeight + 20) return el;
  }
  for (const sel of NuviieMaps.SCROLL_CONTAINER_SELECTORS) {
    const el = document.querySelector(sel);
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
  const h1 = document.querySelector('[role="main"] h1.DUwDvf')
    || document.querySelector('[role="main"] h1')
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
  }, maxMs, 100);

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

NuviieMaps.hasWebResultsContent = () => {
  const detailRoot = document.querySelector('[role="main"]') || document.body;
  const headings = ['Resultados da Web', 'Web results', 'Resultados web'];
  for (const el of detailRoot.querySelectorAll('h2, div.fontHeadlineSmall')) {
    const t = (el.textContent || '').trim();
    if (headings.some((h) => t === h || t.startsWith(h))) {
      const section = el.closest('div')?.parentElement || el.parentElement;
      if (section?.querySelector('a[href*="instagram.com"], a[href*="facebook.com"], a[href*="linkedin.com"], .CIdPsb, .RMrS6d')) {
        return true;
      }
    }
  }
  return detailRoot.querySelector(
    'a[href*="instagram.com"], a[href*="facebook.com"], a[href*="linkedin.com"]'
  ) !== null;
};

NuviieMaps.scrollUntilSection = async (labels, maxMs = 8000) => {
  const labelList = Array.isArray(labels) ? labels : [labels];
  const deadline = Date.now() + maxMs;
  let step = 0;

  while (Date.now() < deadline) {
    const container = NuviieMaps.getDetailScrollContainer();
    if (NuviieMaps.hasWebResultsContent()) return true;

    if (container) {
      const maxScroll = container.scrollHeight - container.clientHeight;
      if (maxScroll <= 0 || container.scrollTop >= maxScroll - 50) {
        await NuviieMaps.sleep(300);
        if (NuviieMaps.hasWebResultsContent()) return true;
        break;
      }
      const increment = Math.max(280, Math.floor(container.clientHeight * 0.75));
      container.scrollTop = Math.min(container.scrollTop + increment, maxScroll);
    } else {
      NuviieMaps.setScrollTop(400 + step * 600);
    }

    step += 1;
    await NuviieMaps.sleep(180);
  }

  for (const el of (document.querySelector('[role="main"]') || document.body).querySelectorAll('h2')) {
    const t = (el.textContent || '').trim();
    if (labelList.some((lbl) => t === lbl || t.startsWith(lbl))) {
      el.scrollIntoView({ block: 'end', behavior: 'instant' });
      await NuviieMaps.sleep(350);
      return NuviieMaps.hasWebResultsContent();
    }
  }

  NuviieMaps.setScrollTop(999999);
  await NuviieMaps.sleep(400);
  return NuviieMaps.hasWebResultsContent();
};

NuviieMaps.scrollPanel = async ({ light = false } = {}) => {
  if (light) {
    for (const stepPx of [300, 900, 99999]) {
      NuviieMaps.setScrollTop(stepPx);
      await NuviieMaps.sleep(250);
    }
    NuviieMaps.setScrollTop(0);
    await NuviieMaps.sleep(200);
    return;
  }
  await NuviieMaps.scrollUntilSection(['Resultados da Web', 'Web results'], 6000);
  NuviieMaps.setScrollTop(0);
  await NuviieMaps.sleep(300);
};

NuviieMaps.expandHours = async () => {
  const detailRoot = document.querySelector('[role="main"]') || document;
  const selectors = [
    'div.OMl5r[jsaction*="openhours"][aria-expanded="false"]',
    'div.OMl5r[aria-expanded="false"]',
    'div[jsaction*="openhours"][aria-expanded="false"]',
  ];
  for (const sel of selectors) {
    const el = detailRoot.querySelector(sel);
    if (el) {
      el.click();
      await NuviieMaps.sleep(350);
      return;
    }
  }
};

NuviieMaps.clickTab = async (labels) => {
  const detailRoot = document.querySelector('[role="main"]')?.closest('.bJzME')
    || document.querySelector('.bJzME')
    || document;
  for (const label of labels) {
    for (const tab of detailRoot.querySelectorAll('[role="tab"], button.hh2c6')) {
      const t = (tab.textContent || tab.getAttribute('aria-label') || '').trim();
      if (t === label || t.toLowerCase() === label.toLowerCase() || (tab.getAttribute('aria-label') || '').includes(label)) {
        tab.click();
        await NuviieMaps.sleep(500);
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
  await NuviieMaps.sleep(400);
  return amenities;
};

NuviieMaps.visitReviewsTab = async ({ fast = false } = {}) => {
  const ok = await NuviieMaps.clickTab(['Avaliações', 'Avaliacoes']);
  if (!ok) {
    return NuviieMaps.extractReviews();
  }
  await NuviieMaps.scrollPanel({ light: true });
  if (!fast) {
    document.querySelectorAll(
      'button[aria-label*="Ver mais"], button.w8nwRe, button[jsaction*="reviewfulltext"]'
    ).forEach((btn) => {
      try { btn.click(); } catch { /* ignore */ }
    });
    await NuviieMaps.sleep(300);
  }
  const reviews = NuviieMaps.extractReviews();
  await NuviieMaps.goToOverview();
  await NuviieMaps.sleep(400);
  return reviews;
};

NuviieMaps.scrollToWebResults = async () => {
  await NuviieMaps.scrollUntilSection(['Resultados da Web', 'Web results'], 5000);
};

NuviieMaps.scrollToTopContact = async () => {
  NuviieMaps.setScrollTop(0);
  await NuviieMaps.sleep(300);
};

NuviieMaps.revealContactButtons = async () => {
  const detailRoot = document.querySelector('[role="main"]') || document;
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
        await NuviieMaps.sleep(200);
      } catch { /* ignore */ }
    }
  }
};

NuviieMaps.waitForStableH1 = async (maxAttempts = 25) => {
  for (let i = 0; i < maxAttempts; i++) {
    const text = NuviieMaps.getDetailH1Text();
    if (NuviieMaps.isValidPlaceName(text) && text.toLowerCase() !== 'resultados') return text;
    await NuviieMaps.sleep(200);
  }
  return NuviieMaps.nameFromUrl(window.location.href) || '';
};

NuviieMaps.clickPlaceLink = async (linkInfo) => {
  if (linkInfo.element && document.contains(linkInfo.element)) {
    linkInfo.element.scrollIntoView({ block: 'center', behavior: 'instant' });
    linkInfo.element.click();
    await NuviieMaps.sleep(600);
    return true;
  }
  const anchor = [...document.querySelectorAll('a[href*="/maps/place/"]')].find(
    (a) => NuviieMaps.basePlaceUrl(a.href) === linkInfo.base
  );
  if (anchor) {
    anchor.scrollIntoView({ block: 'center', behavior: 'instant' });
    anchor.click();
    await NuviieMaps.sleep(600);
    return true;
  }
  return false;
};
