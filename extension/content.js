/* global NuviieMaps, chrome */
window.NuviieMaps = window.NuviieMaps || {};

NuviieMaps.state = {
  running: false,
  stopRequested: false,
  leads: [],
  skippedPlaces: 0,
  progress: { current: 0, total: 0, status: 'idle', message: '' },
};

NuviieMaps.sendProgress = () => {
  chrome.runtime.sendMessage({
    type: 'PROGRESS',
    progress: { ...NuviieMaps.state.progress },
    leadsCount: NuviieMaps.state.leads.length,
    skippedPlaces: NuviieMaps.state.skippedPlaces,
  }).catch(() => {});
};

NuviieMaps.extractSinglePlace = async (linkInfo, options) => {
  NuviieMaps._webResultsCtx = null;

  const clicked = await NuviieMaps.clickPlaceLink(linkInfo);
  if (!clicked) return null;

  const urlMatches = linkInfo.base && NuviieMaps.basePlaceUrl(window.location.href) === linkInfo.base;
  const ready = await NuviieMaps.waitForPlaceReady(linkInfo, urlMatches ? 5000 : 8000);
  if (!ready.name) return null;

  // Fase A — contato no topo (telefone, site, wa.me)
  NuviieMaps.setScrollTop(0);
  await NuviieMaps.sleep(150);
  await NuviieMaps.expandHours();
  await NuviieMaps.revealContactButtons();

  const detailRoot = NuviieMaps.getDetailPanelRoot();
  let contactSnapshot = NuviieMaps.mergeExtractData(
    NuviieMaps.extractContactFields(),
    NuviieMaps.extractPhoneFromPanel(detailRoot),
  );

  // Fase B — scroll até Resultados da Web + extração completa
  await NuviieMaps.scrollUntilWebResultsComplete(5500);
  await NuviieMaps.waitForWebResultsIframe(ready.name, 2500);

  let jsData = NuviieMaps.extractAll();
  jsData = NuviieMaps.mergeExtractData(jsData, contactSnapshot);
  NuviieMaps.extractDeepSocialLinks(NuviieMaps.getDetailPanelRoot(), jsData);
  jsData.name = ready.name;
  jsData._extract_warnings = ready.warnings;

  if (!jsData.phone || !jsData.facebook) {
    NuviieMaps.setScrollTop(0);
    await NuviieMaps.sleep(150);
    const topRetry = NuviieMaps.mergeExtractData(
      NuviieMaps.extractContactFields(),
      NuviieMaps.extractPhoneFromPanel(NuviieMaps.getDetailPanelRoot()),
    );
    await NuviieMaps.scrollUntilWebResultsComplete(3500);
    const bottomRetry = NuviieMaps.extractAll();
    NuviieMaps.extractDeepSocialLinks(NuviieMaps.getDetailPanelRoot(), bottomRetry);
    jsData = NuviieMaps.mergeExtractData(jsData, NuviieMaps.mergeExtractData(bottomRetry, topRetry));
    jsData.name = ready.name;
  }

  let aboutAmenities = [];
  let reviews = [];
  if (options.includeExtras) {
    aboutAmenities = await NuviieMaps.visitAboutTab();
    reviews = await NuviieMaps.visitReviewsTab({ fast: true });
    NuviieMaps.setScrollTop(0);
    const extra = NuviieMaps.extractAll();
    NuviieMaps.extractDeepSocialLinks(NuviieMaps.getDetailPanelRoot(), extra);
    jsData = NuviieMaps.mergeExtractData(jsData, extra);
    jsData.name = ready.name;
  }

  const hoursExtra = NuviieMaps.extractHours();
  const mapsUrl = linkInfo.href || window.location.href;

  return NuviieMaps.mapToLead(jsData, {
    city: options.city,
    niche: options.niche,
    mapsUrl,
    placeKey: linkInfo.base,
    expectedName: ready.fromUrl || ready.name,
    reviews,
    aboutAmenities,
    hoursExtra,
    extractWarnings: ready.warnings,
  });
};

NuviieMaps.runExtraction = async (options) => {
  if (NuviieMaps.state.running) {
    return { ok: false, error: 'Extração já em andamento.' };
  }

  NuviieMaps.state.running = true;
  NuviieMaps.state.stopRequested = false;
  NuviieMaps.state.leads = [];
  NuviieMaps.state.skippedPlaces = 0;

  const limit = options.limit > 0 ? options.limit : 9999;
  const links = NuviieMaps.collectPlaceLinks().slice(0, limit);

  if (!links.length) {
    NuviieMaps.state.running = false;
    NuviieMaps.state.progress = { current: 0, total: 0, status: 'error', message: 'Nenhum lugar encontrado. Role a lista no Maps primeiro.' };
    NuviieMaps.sendProgress();
    return { ok: false, error: NuviieMaps.state.progress.message };
  }

  NuviieMaps.state.progress = {
    current: 0,
    total: links.length,
    status: 'running',
    message: `Extraindo 0/${links.length}...`,
  };
  NuviieMaps.sendProgress();

  const seenPlaces = new Set();

  for (let i = 0; i < links.length; i++) {
    if (NuviieMaps.state.stopRequested) break;

    const link = links[i];
    NuviieMaps.state.progress = {
      current: i,
      total: links.length,
      status: 'running',
      message: `Extraindo ${i + 1}/${links.length}...`,
    };
    NuviieMaps.sendProgress();

    try {
      const lead = await NuviieMaps.extractSinglePlace(link, options);
      const placeKey = lead?._place_key || link.base;
      if (lead && placeKey && !seenPlaces.has(placeKey)) {
        seenPlaces.add(placeKey);
        NuviieMaps.state.leads.push(lead);
      } else if (!lead) {
        NuviieMaps.state.skippedPlaces += 1;
      }
    } catch (err) {
      console.warn('[NuviieMaps] Erro no lugar', link.base, err);
      NuviieMaps.state.skippedPlaces += 1;
    }

    NuviieMaps.state.progress.current = i + 1;
    NuviieMaps.sendProgress();
    await NuviieMaps.randomDelay(options.delayMin || 300, options.delayMax || 600);
  }

  NuviieMaps.state.running = false;
  const stopped = NuviieMaps.state.stopRequested;
  const skippedMsg = NuviieMaps.state.skippedPlaces
    ? ` (${NuviieMaps.state.skippedPlaces} ignorados)`
    : '';
  NuviieMaps.state.progress = {
    current: NuviieMaps.state.progress.current,
    total: links.length,
    status: stopped ? 'stopped' : 'done',
    message: stopped
      ? `Parado. ${NuviieMaps.state.leads.length} leads extraídos${skippedMsg}.`
      : `Concluído! ${NuviieMaps.state.leads.length}/${links.length} leads extraídos${skippedMsg}.`,
  };
  NuviieMaps.sendProgress();

  chrome.runtime.sendMessage({
    type: 'EXTRACTION_DONE',
    leads: NuviieMaps.state.leads,
    progress: NuviieMaps.state.progress,
    skippedPlaces: NuviieMaps.state.skippedPlaces,
  }).catch(() => {});

  return { ok: true, leads: NuviieMaps.state.leads, progress: NuviieMaps.state.progress };
};

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'START_EXTRACTION') {
    NuviieMaps.runExtraction(msg.options || {}).then(sendResponse);
    return true;
  }
  if (msg.type === 'STOP_EXTRACTION') {
    NuviieMaps.state.stopRequested = true;
    sendResponse({ ok: true });
    return false;
  }
  if (msg.type === 'GET_STATE') {
    sendResponse({
      running: NuviieMaps.state.running,
      leads: NuviieMaps.state.leads,
      progress: NuviieMaps.state.progress,
      detectedCity: NuviieMaps.detectCityFromPage(),
      placeCount: NuviieMaps.collectPlaceLinks().length,
      skippedPlaces: NuviieMaps.state.skippedPlaces,
    });
    return false;
  }
  return false;
});
