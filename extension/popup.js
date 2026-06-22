const NM = {
  mode: 'maps',
  leads: [],
  extracting: false,
  progress: { current: 0, total: 0, status: 'idle', message: 'Pronto.' },
};

let progressPollTimer = null;
let toastTimer = null;

function showVersion() {
  try {
    const version = chrome.runtime.getManifest().version;
    const el = document.getElementById('extVersion');
    if (el && version) el.textContent = `v${version}`;
  } catch {
    /* ignore */
  }
}

function showToast(message, kind = 'info', durationMs = 5000) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = message;
  el.className = `toast show${kind ? ` ${kind}` : ''}`;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.classList.remove('show');
  }, durationMs);
}

async function notifyKanbanRefresh(detail) {
  const patterns = ['http://127.0.0.1:8000/*', 'http://localhost:8000/*'];
  try {
    const tabs = await chrome.tabs.query({ url: patterns });
    await Promise.all(
      tabs.map((tab) => chrome.tabs.sendMessage(tab.id, {
        type: 'NUVIIE_LEADS_UPDATED',
        ...detail,
      }).catch(() => {})),
    );
  } catch {
    /* ignore */
  }
}

function stopProgressPoll() {
  if (progressPollTimer) {
    clearInterval(progressPollTimer);
    progressPollTimer = null;
  }
}

function startProgressPoll() {
  stopProgressPoll();
  progressPollTimer = setInterval(async () => {
    if (NM.mode !== 'instagram') return;
    try {
      const local = await chrome.storage.local.get(['nuviieProgress', 'nuviieLeads', 'nuviieMode']);
      if (local.nuviieMode !== 'instagram' || !local.nuviieProgress) return;
      applyProgressUpdate(local.nuviieProgress, (local.nuviieLeads || []).length);
      if (local.nuviieProgress.status === 'done' || local.nuviieProgress.status === 'error' || local.nuviieProgress.status === 'stopped') {
        NM.leads = local.nuviieLeads || [];
        setToggleButton(false);
        stopProgressPoll();
      }
    } catch {
      /* ignore poll errors */
    }
  }, 400);
}

function applyProgressUpdate(progress, leadsCount) {
  if (!progress) return;
  NM.progress = progress;
  setProgress(progress.current, progress.total);
  setStatus(progress.message, progress.status);
  document.getElementById('leadCount').textContent = String(leadsCount ?? NM.leads.length);
  const running = progress.status === 'running';
  if (running !== NM.extracting) setToggleButton(running);
}

function setToggleButton(running) {
  NM.extracting = !!running;
  const btn = document.getElementById('btnToggle');
  const label = document.getElementById('btnToggleLabel');
  const icon = document.getElementById('btnToggleIcon');
  if (!btn || !label || !icon) return;

  if (NM.extracting) {
    btn.classList.remove('primary');
    btn.classList.add('danger');
    label.textContent = 'Parar';
    icon.innerHTML = '<rect x="6" y="6" width="12" height="12" rx="1"/>';
  } else {
    btn.classList.remove('danger');
    btn.classList.add('primary');
    label.textContent = NM.mode === 'instagram' ? 'Extrair Instagram' : 'Extrair';
    icon.innerHTML = '<polygon points="5 3 19 12 5 21 5 3"/>';
  }
}

function formatLeadFieldSummary(lead) {
  if (!lead) return '';
  const shortName = (lead.name || 'Lead').split(/\s+/).slice(0, 2).join(' ');
  const labels = {
    phone: 'tel',
    website: 'web',
    instagram: 'ig',
    facebook: 'fb',
    youtube: 'yt',
    twitter: 'tw',
    linkedin: 'li',
  };
  const found = new Set(lead._fields_found || []);
  if (lead.normalized_phone || lead.phone_number) found.add('phone');
  if (lead.website) found.add('website');
  if (lead.instagram) found.add('instagram');
  if (lead.facebook) found.add('facebook');
  if (lead.youtube) found.add('youtube');
  if (lead.twitter) found.add('twitter');
  if (lead.linkedin) found.add('linkedin');

  const parts = ['phone', 'instagram', 'facebook', 'website'].map((key) => {
    const ok = found.has(key);
    return `${labels[key]} ${ok ? '✓' : '✗'}`;
  });
  return `${shortName} — ${parts.join(' ')}`;
}

function summarizeExtractionFields(leads) {
  if (!leads?.length) return '';
  const last = leads[leads.length - 1];
  const summary = formatLeadFieldSummary(last);
  if (leads.length === 1) return summary;
  return `${summary} (+${leads.length - 1} outros)`;
}

function parseOptionalInt(value) {
  if (value === '' || value == null) return null;
  const n = parseInt(value, 10);
  return Number.isNaN(n) ? null : n;
}

function readInstagramFiltersFromForm() {
  return {
    websiteFilter: document.getElementById('websiteFilter')?.value || 'any',
    minFollowers: parseOptionalInt(document.getElementById('minFollowers')?.value),
    maxFollowers: parseOptionalInt(document.getElementById('maxFollowers')?.value),
    minPosts: parseOptionalInt(document.getElementById('minPosts')?.value),
    maxPosts: parseOptionalInt(document.getElementById('maxPosts')?.value),
    lastPostWithin: document.getElementById('lastPostWithin')?.value || 'any',
  };
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function sendToMapsTab(message) {
  const tab = await getActiveTab();
  if (!tab?.id) throw new Error('Abra uma aba do Google Maps.');
  if (!tab.url?.includes('google.com/maps')) {
    throw new Error('Esta aba não é o Google Maps.');
  }
  return chrome.tabs.sendMessage(tab.id, message);
}

function setStatus(text, kind = '') {
  const el = document.getElementById('status');
  document.getElementById('statusText').textContent = text;
  el.className = kind ? `status ${kind}` : 'status';
}

function setProgress(current, total) {
  const bar = document.getElementById('progressBar');
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  bar.style.width = `${pct}%`;
  document.getElementById('progressText').textContent = total > 0 ? `${current}/${total}` : '—';
}

function updateFilterHint() {
  const hint = document.getElementById('filterBioLinkHint');
  const onlyWithBioLink = document.getElementById('onlyWithBioLink');
  if (!hint || !onlyWithBioLink) return;
  hint.classList.toggle('hidden', NM.mode !== 'instagram' || !onlyWithBioLink.checked);
}

function applyModeUI(mode) {
  NM.mode = mode;
  document.getElementById('tabMaps').classList.toggle('active', mode === 'maps');
  document.getElementById('tabInstagram').classList.toggle('active', mode === 'instagram');
  document.body.classList.toggle('mode-instagram', mode === 'instagram');
  document.body.classList.toggle('mode-maps', mode === 'maps');

  const nicheLabel = document.getElementById('nicheLabel');
  const limitLabel = document.getElementById('limitLabel');
  const btnToggleLabel = document.getElementById('btnToggleLabel');
  const nicheInput = document.getElementById('niche');
  const limitInput = document.getElementById('limit');

  if (mode === 'instagram') {
    nicheLabel.textContent = 'Nicho / segmento *';
    limitLabel.textContent = 'Quantidade de perfis';
    if (btnToggleLabel && !NM.extracting) btnToggleLabel.textContent = 'Extrair Instagram';
    nicheInput.placeholder = 'Ex: dentista';
    limitInput.placeholder = '20';
    limitInput.min = '1';
    setStatus('Informe nicho e cidade. Login no Instagram necessário.');
  } else {
    nicheLabel.textContent = 'Nicho / segmento';
    limitLabel.textContent = 'Limite (0 = todos visíveis)';
    if (btnToggleLabel && !NM.extracting) btnToggleLabel.textContent = 'Extrair';
    nicheInput.placeholder = 'Ex: advogado';
    limitInput.placeholder = '0';
    limitInput.min = '0';
    setStatus('Abra o Google Maps, busque, role a lista e clique Extrair.');
  }
  updateFilterHint();
}

async function loadSettings() {
  const data = await chrome.storage.sync.get({
    city: '',
    niche: '',
    limit: 0,
    instagramLimit: 20,
    nuviieUrl: 'http://127.0.0.1:8000',
    nuviieToken: '',
    onlyVerified: false,
    onlyWithBioLink: false,
    websiteFilter: 'any',
    minFollowers: '',
    maxFollowers: '',
    minPosts: '',
    maxPosts: '',
    lastPostWithin: 'any',
    includeExtras: false,
    snowball: true,
    skipExisting: true,
    mode: 'maps',
  });
  const local = await chrome.storage.local.get({
    nuviieLeads: [],
    nuviieProgress: null,
    nuviieMode: 'maps',
  });

  document.getElementById('city').value = data.city;
  document.getElementById('niche').value = data.niche;
  document.getElementById('nuviieUrl').value = data.nuviieUrl;
  document.getElementById('nuviieToken').value = data.nuviieToken;
  document.getElementById('onlyVerified').checked = data.onlyVerified;
  document.getElementById('onlyWithBioLink').checked = data.onlyWithBioLink;
  document.getElementById('websiteFilter').value = data.websiteFilter || 'any';
  document.getElementById('minFollowers').value = data.minFollowers ?? '';
  document.getElementById('maxFollowers').value = data.maxFollowers ?? '';
  document.getElementById('minPosts').value = data.minPosts ?? '';
  document.getElementById('maxPosts').value = data.maxPosts ?? '';
  document.getElementById('lastPostWithin').value = data.lastPostWithin || 'any';
  const includeExtrasEl = document.getElementById('includeExtras');
  if (includeExtrasEl) includeExtrasEl.checked = !!data.includeExtras;
  const snowballEl = document.getElementById('snowball');
  if (snowballEl) snowballEl.checked = data.snowball !== false;
  const skipExistingEl = document.getElementById('skipExisting');
  if (skipExistingEl) skipExistingEl.checked = data.skipExisting !== false;

  const mode = local.nuviieMode || data.mode || 'maps';
  applyModeUI(mode);

  if (mode === 'instagram') {
    document.getElementById('limit').value = data.instagramLimit || 20;
    NM.leads = local.nuviieLeads || [];
    NM.progress = local.nuviieProgress || NM.progress;
  } else {
    document.getElementById('limit').value = data.limit || '';
  }

  updateFilterHint();
  return { ...data, mode };
}

async function saveSettings() {
  const mode = NM.mode;
  const igFilters = readInstagramFiltersFromForm();
  const payload = {
    city: document.getElementById('city').value.trim(),
    niche: document.getElementById('niche').value.trim(),
    nuviieUrl: document.getElementById('nuviieUrl').value.trim().replace(/\/$/, ''),
    nuviieToken: document.getElementById('nuviieToken').value.trim(),
    onlyVerified: document.getElementById('onlyVerified').checked,
    onlyWithBioLink: document.getElementById('onlyWithBioLink').checked,
    websiteFilter: igFilters.websiteFilter,
    minFollowers: document.getElementById('minFollowers').value,
    maxFollowers: document.getElementById('maxFollowers').value,
    minPosts: document.getElementById('minPosts').value,
    maxPosts: document.getElementById('maxPosts').value,
    lastPostWithin: igFilters.lastPostWithin,
    includeExtras: document.getElementById('includeExtras')?.checked || false,
    snowball: document.getElementById('snowball')?.checked !== false,
    skipExisting: document.getElementById('skipExisting')?.checked !== false,
    mode,
  };
  const limitVal = parseInt(document.getElementById('limit').value, 10);
  if (mode === 'instagram') {
    payload.instagramLimit = limitVal > 0 ? limitVal : 20;
  } else {
    payload.limit = limitVal || 0;
  }
  await chrome.storage.sync.set(payload);
  payload.instagramFilters = igFilters;
  return payload;
}

function leadsToCsv(leads) {
  const cols = [
    'name', 'category', 'city', 'phone_number', 'normalized_phone', 'website',
    'website_detected_type', 'instagram', 'facebook', 'youtube', 'twitter', 'linkedin',
    'address', 'rating', 'review_count', 'maps_url', 'maps_share_url', 'bio',
    'profile_picture_url', 'is_verified', 'source',
    'business_hours', 'recent_reviews', '_amenities', '_plus_code', '_price_range',
  ];
  const esc = (v) => {
    const s = v == null ? '' : (typeof v === 'object' ? JSON.stringify(v) : String(v));
    return `"${s.replace(/"/g, '""')}"`;
  };
  const rows = [cols.join(',')];
  leads.forEach((lead) => {
    rows.push(cols.map((c) => esc(lead[c])).join(','));
  });
  return rows.join('\n');
}

function downloadFile(filename, content, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  chrome.downloads.download({ url, filename, saveAs: true }, () => {
    URL.revokeObjectURL(url);
  });
}

async function refreshMapsState() {
  try {
    const state = await sendToMapsTab({ type: 'GET_STATE' });
    NM.leads = state.leads || [];
    NM.progress = state.progress || NM.progress;
    if (!document.getElementById('city').value && state.detectedCity) {
      document.getElementById('city').value = state.detectedCity;
    }
    document.getElementById('placeCount').textContent = String(state.placeCount || 0);
    setProgress(NM.progress.current, NM.progress.total);
    setStatus(NM.progress.message || 'Pronto.', NM.progress.status);
    document.getElementById('leadCount').textContent = String(NM.leads.length);
    setToggleButton(!!state.running);
  } catch (e) {
    setStatus(e.message, 'error');
  }
}

async function refreshInstagramState() {
  try {
    const state = await chrome.runtime.sendMessage({ type: 'GET_INSTAGRAM_STATE' });
    if (state) {
      NM.leads = state.leads || [];
      NM.progress = state.progress || NM.progress;
      applyProgressUpdate(NM.progress, NM.leads.length);
      setToggleButton(!!state.running);
      if (state.running) startProgressPoll();
    }
  } catch (e) {
    setStatus('Recarregue a extensão em chrome://extensions e tente de novo.', 'error');
  }
}

async function refreshState() {
  if (NM.mode === 'instagram') {
    await refreshInstagramState();
  } else {
    await refreshMapsState();
  }
}

document.getElementById('tabMaps').addEventListener('click', async () => {
  applyModeUI('maps');
  await chrome.storage.sync.set({ mode: 'maps' });
  await refreshState();
});

document.getElementById('tabInstagram').addEventListener('click', async () => {
  applyModeUI('instagram');
  await chrome.storage.sync.set({ mode: 'instagram' });
  const data = await chrome.storage.sync.get({ instagramLimit: 20 });
  document.getElementById('limit').value = data.instagramLimit || 20;
  await refreshState();
});

document.getElementById('btnToggle').addEventListener('click', async () => {
  if (NM.extracting) {
    try {
      if (NM.mode === 'instagram') {
        await chrome.runtime.sendMessage({ type: 'STOP_INSTAGRAM_EXTRACTION' });
      } else {
        await sendToMapsTab({ type: 'STOP_EXTRACTION' });
      }
      setStatus('Parando...', 'running');
    } catch (e) {
      setStatus(e.message, 'error');
    }
    return;
  }

  const settings = await saveSettings();
  if (!settings.city) {
    setStatus('Informe a cidade.', 'error');
    return;
  }

  setToggleButton(true);
  setStatus('Iniciando extração...', 'running');

  try {
    if (NM.mode === 'instagram') {
      if (!settings.niche) {
        setStatus('Informe o nicho.', 'error');
        setToggleButton(false);
        return;
      }
      chrome.runtime.sendMessage({
        type: 'START_INSTAGRAM_EXTRACTION',
        options: {
          city: settings.city,
          niche: settings.niche,
          limit: settings.instagramLimit || 20,
          snowball: settings.snowball !== false,
          skipExisting: settings.skipExisting !== false,
          nuviieUrl: settings.nuviieUrl || '',
          nuviieToken: settings.nuviieToken || '',
          filters: {
            onlyVerified: settings.onlyVerified,
            onlyWithBioLink: settings.onlyWithBioLink,
            websiteFilter: settings.websiteFilter,
            minFollowers: settings.instagramFilters.minFollowers,
            maxFollowers: settings.instagramFilters.maxFollowers,
            minPosts: settings.instagramFilters.minPosts,
            maxPosts: settings.instagramFilters.maxPosts,
            lastPostWithin: settings.instagramFilters.lastPostWithin,
          },
        },
      }).then((resp) => {
        if (resp && resp.ok === false) {
          setStatus(resp.error || 'Falha ao iniciar.', 'error');
          setToggleButton(false);
          stopProgressPoll();
        }
      }).catch((e) => {
        setStatus(
          e.message?.includes('Receiving end') || e.message?.includes('Extension context invalidated')
            ? 'Extensão desatualizada. Recarregue em chrome://extensions.'
            : (e.message || 'Erro ao iniciar extração.'),
          'error',
        );
        setToggleButton(false);
        stopProgressPoll();
      });
      startProgressPoll();
    } else {
      await sendToMapsTab({
        type: 'START_EXTRACTION',
        options: {
          city: settings.city,
          niche: settings.niche,
          limit: settings.limit,
          delayMin: 300,
          delayMax: 600,
          includeExtras: settings.includeExtras,
        },
      });
      setToggleButton(true);
    }
  } catch (e) {
    setStatus(e.message, 'error');
    setToggleButton(false);
  }
});

document.getElementById('btnExportJson').addEventListener('click', () => {
  if (!NM.leads.length) { setStatus('Nenhum lead para exportar.', 'error'); return; }
  const prefix = NM.mode === 'instagram' ? 'nuviie-instagram' : 'nuviie-leads';
  downloadFile(`${prefix}-${Date.now()}.json`, JSON.stringify(NM.leads, null, 2), 'application/json');
});

document.getElementById('btnExportCsv').addEventListener('click', () => {
  if (!NM.leads.length) { setStatus('Nenhum lead para exportar.', 'error'); return; }
  const prefix = NM.mode === 'instagram' ? 'nuviie-instagram' : 'nuviie-leads';
  downloadFile(`${prefix}-${Date.now()}.csv`, leadsToCsv(NM.leads), 'text/csv');
});

document.getElementById('btnSendNuviie').addEventListener('click', async () => {
  const settings = await saveSettings();
  if (!NM.leads.length) {
    setStatus('Nenhum lead para enviar.', 'error');
    showToast('Nenhum lead para enviar.', 'error');
    return;
  }
  if (!settings.nuviieToken) {
    setStatus('Configure o token do Nuviie.', 'error');
    showToast('Configure o token do Nuviie.', 'error');
    return;
  }
  const btn = document.getElementById('btnSendNuviie');
  btn.disabled = true;
  setStatus('Enviando ao Nuviie...', 'running');
  showToast('Enviando ao Nuviie...', 'running', 60000);
  try {
    const resp = await fetch(`${settings.nuviieUrl}/api/leads/bulk-import/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Nuviie-Token': settings.nuviieToken,
      },
      body: JSON.stringify({ city: settings.city, leads: NM.leads }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || data.detail || 'Falha no envio');
    const parts = [];
    if (data.saved) parts.push(`${data.saved} novo${data.saved > 1 ? 's' : ''}`);
    if (data.updated) parts.push(`${data.updated} atualizado${data.updated > 1 ? 's' : ''}`);
    if (data.skipped) parts.push(`${data.skipped} já existia${data.skipped > 1 ? 'm' : ''}`);
    const msg = parts.length
      ? `Enviado com sucesso! ${parts.join(', ')}.`
      : 'Enviado — nenhuma alteração no banco.';
    setStatus(msg, 'done');
    showToast(msg, 'success', 6000);
    await notifyKanbanRefresh({ saved: data.saved, updated: data.updated, skipped: data.skipped });
  } catch (e) {
    const msg = e.message || 'Erro ao enviar ao Nuviie.';
    setStatus(msg, 'error');
    showToast(msg, 'error', 7000);
  } finally {
    btn.disabled = false;
  }
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'PROGRESS') {
    if (msg.mode === 'instagram' && NM.mode !== 'instagram') return;
    if (msg.mode === 'instagram') {
      applyProgressUpdate(msg.progress, msg.leadsCount);
      setToggleButton(msg.progress?.status === 'running');
      return;
    }
    if (NM.mode === 'instagram') return;
    NM.progress = msg.progress;
    setProgress(msg.progress.current, msg.progress.total);
    setStatus(msg.progress.message, msg.progress.status);
    document.getElementById('leadCount').textContent = String(msg.leadsCount || 0);
    setToggleButton(msg.progress?.status === 'running');
  }
  if (msg.type === 'EXTRACTION_DONE') {
    if (msg.mode === 'instagram' && NM.mode !== 'instagram') return;
    if (msg.mode !== 'instagram' && NM.mode === 'instagram') return;
    NM.leads = msg.leads || [];
    NM.progress = msg.progress;
    setToggleButton(false);
    applyProgressUpdate(NM.progress, NM.leads.length);
    const fieldSummary = summarizeExtractionFields(NM.leads);
    let statusMsg = NM.progress?.message || 'Concluído.';
    if (fieldSummary) statusMsg = `${statusMsg} · ${fieldSummary}`;
    setStatus(statusMsg, NM.progress?.status || 'done');
    if (fieldSummary) showToast(fieldSummary, 'success', 7000);
    stopProgressPoll();
  }
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== 'local' || NM.mode !== 'instagram') return;
  if (changes.nuviieProgress?.newValue) {
    const leads = changes.nuviieLeads?.newValue || NM.leads;
    applyProgressUpdate(changes.nuviieProgress.newValue, leads.length);
  }
  if (changes.nuviieLeads?.newValue) {
    NM.leads = changes.nuviieLeads.newValue;
    document.getElementById('leadCount').textContent = String(NM.leads.length);
  }
});

loadSettings().then(refreshState);
showVersion();

document.getElementById('onlyWithBioLink')?.addEventListener('change', updateFilterHint);
