/* global NuviieMaps */
window.NuviieMaps = window.NuviieMaps || {};

NuviieMaps.scrollPanel = async ({ light = false } = {}) => {
  const scrollScript = (scrollTop) => {
    const containers = [
      document.querySelector('div[role="main"]'),
      document.querySelector('.DxyBCb'),
      document.querySelector('.bJzME'),
      document.querySelector('.siAUzd'),
      document.querySelector('[jsrenderer="lutinne"]'),
      document.querySelector('.TIHn2'),
      document.querySelector('[aria-label][role="region"]'),
    ];
    const p = containers.find((c) => c && c.scrollHeight > window.innerHeight);
    if (p) p.scrollTop = scrollTop;
    else window.scrollTo(0, scrollTop);
  };

  if (light) {
    // Scroll leve para abas Sobre e Avaliações — conteúdo mais curto,
    // não precisa de lazy-load de "Resultados da Web"
    const lightSteps = [300, 800, 1800, 99999];
    for (const stepPx of lightSteps) {
      scrollScript(stepPx);
      await NuviieMaps.sleep(500);
    }
    scrollScript(0);
    await NuviieMaps.sleep(300);
    return;
  }

  // Scroll completo para a aba principal (overview) — carrega lazy-load de redes sociais
  const steps = [200, 500, 900, 1400, 2000, 2800, 3800, 5000, 6500, 8500, 12000, 99999];
  for (const stepPx of steps) {
    scrollScript(stepPx);
    await NuviieMaps.sleep(800);
  }

  // A seção "Resultados da Web" (com links de Instagram/LinkedIn/Facebook
  // encontrados via busca) é carregada via JS de forma mais lenta que o
  // resto do painel. Damos um "ressalto" (sobe um pouco e desce de novo)
  // para forçar o disparo do lazy-load, e esperamos mais tempo no fundo.
  scrollScript(99999 - 600);
  await NuviieMaps.sleep(400);
  scrollScript(99999);
  await NuviieMaps.sleep(1500); // era 3000ms — 1500ms já é suficiente

  const containers = [
    document.querySelector('div[role="main"]'),
    document.querySelector('.DxyBCb'),
    document.querySelector('.bJzME'),
    document.querySelector('.siAUzd'),
  ];
  const p = containers.find((c) => c && c.scrollHeight > window.innerHeight);
  if (p) p.scrollTop = 0;
  else window.scrollTo(0, 0);
  await NuviieMaps.sleep(500);
};

NuviieMaps.expandHours = async () => {
  const selectors = [
    'div.OMl5r[jsaction*="openhours"][aria-expanded="false"]',
    'div.OMl5r[aria-expanded="false"]',
    'div[jsaction*="openhours"][aria-expanded="false"]',
    '[jsaction*="openhours.wfvdle"]',
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el) {
      el.click();
      await NuviieMaps.sleep(600);
      return;
    }
  }
};

NuviieMaps.clickTab = async (labels) => {
  for (const label of labels) {
    const candidates = [
      `button[aria-label="${label}"]`,
      `[role="tab"][aria-label="${label}"]`,
    ];
    for (const sel of candidates) {
      const btn = document.querySelector(sel);
      if (btn) {
        btn.click();
        await NuviieMaps.sleep(1200);
        return true;
      }
    }
    for (const tab of document.querySelectorAll('[role="tab"], button.hh2c6')) {
      const t = (tab.textContent || tab.getAttribute('aria-label') || '').trim();
      if (t === label || t.toLowerCase() === label.toLowerCase()) {
        tab.click();
        await NuviieMaps.sleep(1200);
        return true;
      }
    }
  }
  return false;
};

NuviieMaps.goToOverview = () => NuviieMaps.clickTab(['Visão geral', 'Visao geral']);

NuviieMaps.visitAboutTab = async () => {
  const ok = await NuviieMaps.clickTab(['Sobre']);
  if (!ok) return [];
  await NuviieMaps.scrollPanel({ light: true });
  const amenities = NuviieMaps.extractAboutAmenities();
  await NuviieMaps.goToOverview();
  await NuviieMaps.waitForStableH1();
  return amenities;
};

NuviieMaps.visitReviewsTab = async () => {
  const ok = await NuviieMaps.clickTab(['Avaliações', 'Avaliacoes']);
  if (!ok) {
    return NuviieMaps.extractReviews();
  }
  await NuviieMaps.scrollPanel({ light: true });
  document.querySelectorAll(
    'button[aria-label*="Ver mais"], button.w8nwRe, button[jsaction*="reviewfulltext"]'
  ).forEach((btn) => {
    try { btn.click(); } catch { /* ignore */ }
  });
  await NuviieMaps.sleep(500);
  const reviews = NuviieMaps.extractReviews();
  await NuviieMaps.goToOverview();
  await NuviieMaps.waitForStableH1();
  return reviews;
};

NuviieMaps.scrollToWebResults = async () => {
  const scrollScript = (scrollTop) => {
    const containers = [
      document.querySelector('div[role="main"]'),
      document.querySelector('.DxyBCb'),
      document.querySelector('.bJzME'),
      document.querySelector('.siAUzd'),
    ];
    const p = containers.find((c) => c && c.scrollHeight > window.innerHeight);
    if (p) p.scrollTop = scrollTop;
  };
  // Força lazy-load da seção "Resultados da Web" após voltar da aba Avaliações
  for (const step of [4000, 7000, 99999]) {
    scrollScript(step);
    await NuviieMaps.sleep(600);
  }
  scrollScript(99999);
  await NuviieMaps.sleep(1200);
};

NuviieMaps.scrollToTopContact = async () => {
  const scrollScript = (scrollTop) => {
    const containers = [
      document.querySelector('div[role="main"]'),
      document.querySelector('.DxyBCb'),
      document.querySelector('.bJzME'),
      document.querySelector('.siAUzd'),
    ];
    const p = containers.find((c) => c && c.scrollHeight > window.innerHeight);
    if (p) p.scrollTop = scrollTop;
    else window.scrollTo(0, scrollTop);
  };
  scrollScript(0);
  await NuviieMaps.sleep(800);
};

NuviieMaps.revealContactButtons = async () => {
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
    const btn = document.querySelector(sel);
    if (btn && btn.offsetParent !== null) {
      try {
        btn.click();
        await NuviieMaps.sleep(350);
      } catch { /* ignore */ }
    }
  }
};

NuviieMaps.waitForStableH1 = async (maxAttempts = 25) => {
  for (let i = 0; i < maxAttempts; i++) {
    const h1 = document.querySelector('[role="main"] h1.DUwDvf')
            || document.querySelector('[role="main"] h1')
            || document.querySelector('h1');
    const text = h1 ? h1.textContent.trim() : '';
    if (NuviieMaps.isValidPlaceName(text) && text.toLowerCase() !== 'resultados') return text;
    await NuviieMaps.sleep(300);
  }
  return NuviieMaps.nameFromUrl(window.location.href) || '';
};

NuviieMaps.clickPlaceLink = async (linkInfo) => {
  if (linkInfo.element && document.contains(linkInfo.element)) {
    linkInfo.element.scrollIntoView({ block: 'center', behavior: 'instant' });
    linkInfo.element.click();
    await NuviieMaps.sleep(1500);
    return true;
  }
  const anchor = [...document.querySelectorAll('a[href*="/maps/place/"]')].find(
    (a) => NuviieMaps.basePlaceUrl(a.href) === linkInfo.base
  );
  if (anchor) {
    anchor.scrollIntoView({ block: 'center', behavior: 'instant' });
    anchor.click();
    await NuviieMaps.sleep(1500);
    return true;
  }
  return false;
};