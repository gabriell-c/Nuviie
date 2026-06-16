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

  const ready = await NuviieMaps.waitForPlaceReady(linkInfo);
  if (!ready.name) return null;

  await NuviieMaps.expandHours();
  await NuviieMaps.revealContactButtons();

  await NuviieMaps.scrollUntilSection(['Resultados da Web', 'Web results'], 8000);
  await NuviieMaps.waitForWebResultsIframe(ready.name, 4000);

  let contactSnapshot = NuviieMaps.extractContactFields();
  let jsData = NuviieMaps.extractAll();
  jsData = NuviieMaps.mergeExtractData(jsData, contactSnapshot);
  jsData.name = ready.name;
  jsData._extract_warnings = ready.warnings;

  if (!jsData.facebook && !jsData.instagram && !jsData.linkedin && !jsData.website) {
    await NuviieMaps.scrollUntilSection(['Resultados da Web', 'Web results'], 4000);
    await NuviieMaps.waitForWebResultsIframe(ready.name, 3000);
    const retry = NuviieMaps.extractAll();
    jsData = NuviieMaps.mergeExtractData(jsData, NuviieMaps.mergeExtractData(retry, contactSnapshot));
    jsData.name = ready.name;
  }

  if (!jsData.phone || !jsData.address) {
    await NuviieMaps.revealContactButtons();
    const retry = NuviieMaps.extractAll();
    jsData = NuviieMaps.mergeExtractData(jsData, NuviieMaps.mergeExtractData(retry, contactSnapshot));
    jsData.name = ready.name;
  }

  let aboutAmenities = [];
  let reviews = [];
  if (options.fullExtract !== false) {
    aboutAmenities = await NuviieMaps.visitAboutTab();
    reviews = await NuviieMaps.visitReviewsTab({ fast: true });
    await NuviieMaps.scrollUntilSection(['Resultados da Web', 'Web results'], 4000);
    await NuviieMaps.waitForWebResultsIframe(ready.name, 2500);
    const retryAfterTabs = NuviieMaps.extractAll();
    jsData = NuviieMaps.mergeExtractData(jsData, retryAfterTabs);
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
    await NuviieMaps.randomDelay(options.delayMin || 500, options.delayMax || 1000);
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
