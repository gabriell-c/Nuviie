/* global NuviieMaps, chrome */
window.NuviieMaps = window.NuviieMaps || {};

NuviieMaps.state = {
  running: false,
  stopRequested: false,
  leads: [],
  progress: { current: 0, total: 0, status: 'idle', message: '' },
};

NuviieMaps.sendProgress = () => {
  chrome.runtime.sendMessage({
    type: 'PROGRESS',
    progress: { ...NuviieMaps.state.progress },
    leadsCount: NuviieMaps.state.leads.length,
  }).catch(() => {});
};

NuviieMaps.extractSinglePlace = async (linkInfo, options) => {
  const clicked = await NuviieMaps.clickPlaceLink(linkInfo);
  if (!clicked) return null;

  const name = await NuviieMaps.waitForStableH1();
  if (!name) return null;

  await NuviieMaps.scrollPanel();
  await NuviieMaps.expandHours();

  const aboutAmenities = await NuviieMaps.visitAboutTab();
  const reviews = await NuviieMaps.visitReviewsTab();

  await NuviieMaps.revealContactButtons();
  await NuviieMaps.revealContactButtons();

  let jsData = NuviieMaps.extractAll();
  if (!jsData.phone || !jsData.address) {
    await NuviieMaps.revealContactButtons();
    const retry = NuviieMaps.extractAll();
    jsData = { ...jsData, ...Object.fromEntries(Object.entries(retry).filter(([, v]) => v)) };
  }

  const hoursExtra = NuviieMaps.extractHours();
  const mapsUrl = linkInfo.href || window.location.href;

  return NuviieMaps.mapToLead(jsData, {
    city: options.city,
    niche: options.niche,
    mapsUrl,
    reviews,
    aboutAmenities,
    hoursExtra,
  });
};

NuviieMaps.runExtraction = async (options) => {
  if (NuviieMaps.state.running) {
    return { ok: false, error: 'Extração já em andamento.' };
  }

  NuviieMaps.state.running = true;
  NuviieMaps.state.stopRequested = false;
  NuviieMaps.state.leads = [];

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

  const seenNames = new Set();

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
      if (lead && !seenNames.has(lead.name.toLowerCase())) {
        seenNames.add(lead.name.toLowerCase());
        NuviieMaps.state.leads.push(lead);
      }
    } catch (err) {
      console.warn('[NuviieMaps] Erro no lugar', link.base, err);
    }

    NuviieMaps.state.progress.current = i + 1;
    NuviieMaps.sendProgress();
    await NuviieMaps.randomDelay(options.delayMin || 800, options.delayMax || 1500);
  }

  NuviieMaps.state.running = false;
  const stopped = NuviieMaps.state.stopRequested;
  NuviieMaps.state.progress = {
    current: NuviieMaps.state.progress.current,
    total: links.length,
    status: stopped ? 'stopped' : 'done',
    message: stopped
      ? `Parado. ${NuviieMaps.state.leads.length} leads extraídos.`
      : `Concluído! ${NuviieMaps.state.leads.length} leads extraídos.`,
  };
  NuviieMaps.sendProgress();

  chrome.runtime.sendMessage({
    type: 'EXTRACTION_DONE',
    leads: NuviieMaps.state.leads,
    progress: NuviieMaps.state.progress,
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
    });
    return false;
  }
  return false;
});