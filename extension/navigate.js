/* global NuviieMaps */
window.NuviieMaps = window.NuviieMaps || {};

NuviieMaps.scrollPanel = async () => {
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

  const steps = [200, 500, 900, 1400, 2000, 2800, 3800, 5000, 6500, 8500, 12000, 99999];
  for (const stepPx of steps) {
    scrollScript(stepPx);
    await NuviieMaps.sleep(800);
  }
  await NuviieMaps.sleep(1500);

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
  await NuviieMaps.scrollPanel();
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
  await NuviieMaps.scrollPanel();
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
    const h1 = document.querySelector('h1');
    const text = h1 ? h1.textContent.trim() : '';
    if (NuviieMaps.isValidPlaceName(text)) return text;
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
