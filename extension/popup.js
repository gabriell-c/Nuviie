const NM = {
  leads: [],
  progress: { current: 0, total: 0, status: 'idle', message: 'Pronto.' },
};

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function sendToTab(message) {
  const tab = await getActiveTab();
  if (!tab?.id) throw new Error('Abra uma aba do Google Maps.');
  if (!tab.url?.includes('google.com/maps')) {
    throw new Error('Esta aba não é o Google Maps.');
  }
  return chrome.tabs.sendMessage(tab.id, message);
}

function setStatus(text, kind = '') {
  const el = document.getElementById('status');
  el.textContent = text;
  el.className = kind ? `status ${kind}` : 'status';
}

function setProgress(current, total) {
  const bar = document.getElementById('progressBar');
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  bar.style.width = `${pct}%`;
  document.getElementById('progressText').textContent = total > 0 ? `${current}/${total}` : '—';
}

async function loadSettings() {
  const data = await chrome.storage.sync.get({
    city: '',
    niche: '',
    limit: 0,
    nuviieUrl: 'http://127.0.0.1:8000',
    nuviieToken: '',
    delayMin: 1500,
    delayMax: 3000,
  });
  document.getElementById('city').value = data.city;
  document.getElementById('niche').value = data.niche;
  document.getElementById('limit').value = data.limit || '';
  document.getElementById('nuviieUrl').value = data.nuviieUrl;
  document.getElementById('nuviieToken').value = data.nuviieToken;
  return data;
}

async function saveSettings() {
  const payload = {
    city: document.getElementById('city').value.trim(),
    niche: document.getElementById('niche').value.trim(),
    limit: parseInt(document.getElementById('limit').value, 10) || 0,
    nuviieUrl: document.getElementById('nuviieUrl').value.trim().replace(/\/$/, ''),
    nuviieToken: document.getElementById('nuviieToken').value.trim(),
  };
  await chrome.storage.sync.set(payload);
  return payload;
}

function leadsToCsv(leads) {
  const cols = [
    'name', 'category', 'city', 'phone_number', 'normalized_phone', 'website',
    'instagram', 'facebook', 'youtube', 'twitter', 'linkedin', 'address',
    'rating', 'review_count', 'maps_url', 'maps_share_url', 'bio',
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

async function refreshState() {
  try {
    const state = await sendToTab({ type: 'GET_STATE' });
    NM.leads = state.leads || [];
    NM.progress = state.progress || NM.progress;
    if (!document.getElementById('city').value && state.detectedCity) {
      document.getElementById('city').value = state.detectedCity;
    }
    document.getElementById('placeCount').textContent = String(state.placeCount || 0);
    setProgress(NM.progress.current, NM.progress.total);
    setStatus(NM.progress.message || 'Pronto.', NM.progress.status);
    document.getElementById('leadCount').textContent = String(NM.leads.length);
  } catch (e) {
    setStatus(e.message, 'error');
  }
}

document.getElementById('btnStart').addEventListener('click', async () => {
  const settings = await saveSettings();
  if (!settings.city) {
    setStatus('Informe a cidade.', 'error');
    return;
  }
  setStatus('Iniciando extração...', 'running');
  document.getElementById('btnStart').disabled = true;
  try {
    await sendToTab({
      type: 'START_EXTRACTION',
      options: {
        city: settings.city,
        niche: settings.niche,
        limit: settings.limit,
        delayMin: 1500,
        delayMax: 3000,
      },
    });
  } catch (e) {
    setStatus(e.message, 'error');
    document.getElementById('btnStart').disabled = false;
  }
});

document.getElementById('btnStop').addEventListener('click', async () => {
  try {
    await sendToTab({ type: 'STOP_EXTRACTION' });
    setStatus('Parando...', 'running');
  } catch (e) {
    setStatus(e.message, 'error');
  }
});

document.getElementById('btnExportJson').addEventListener('click', () => {
  if (!NM.leads.length) { setStatus('Nenhum lead para exportar.', 'error'); return; }
  downloadFile(`nuviie-leads-${Date.now()}.json`, JSON.stringify(NM.leads, null, 2), 'application/json');
});

document.getElementById('btnExportCsv').addEventListener('click', () => {
  if (!NM.leads.length) { setStatus('Nenhum lead para exportar.', 'error'); return; }
  downloadFile(`nuviie-leads-${Date.now()}.csv`, leadsToCsv(NM.leads), 'text/csv');
});

document.getElementById('btnSendNuviie').addEventListener('click', async () => {
  const settings = await saveSettings();
  if (!NM.leads.length) { setStatus('Nenhum lead para enviar.', 'error'); return; }
  if (!settings.nuviieToken) { setStatus('Configure o token do Nuviie.', 'error'); return; }
  setStatus('Enviando ao Nuviie...', 'running');
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
    setStatus(`Enviado! ${data.saved} salvos, ${data.skipped} duplicados.`, 'done');
  } catch (e) {
    setStatus(e.message, 'error');
  }
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'PROGRESS') {
    NM.progress = msg.progress;
    setProgress(msg.progress.current, msg.progress.total);
    setStatus(msg.progress.message, msg.progress.status);
    document.getElementById('leadCount').textContent = String(msg.leadsCount || 0);
  }
  if (msg.type === 'EXTRACTION_DONE') {
    NM.leads = msg.leads || [];
    NM.progress = msg.progress;
    document.getElementById('btnStart').disabled = false;
    document.getElementById('leadCount').textContent = String(NM.leads.length);
    setProgress(NM.progress.current, NM.progress.total);
    setStatus(NM.progress.message, NM.progress.status);
  }
});

loadSettings().then(refreshState);
