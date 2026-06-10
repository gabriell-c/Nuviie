/* global NuviieMaps */
window.NuviieMaps = window.NuviieMaps || {};

NuviieMaps.extractHours = () => {
  const hours = {};
  const dayMap = {
    'segunda-feira': 'seg', 'terça-feira': 'ter', 'terca-feira': 'ter',
    'quarta-feira': 'qua', 'quinta-feira': 'qui', 'sexta-feira': 'sex',
    'sábado': 'sab', 'sabado': 'sab', 'domingo': 'dom',
  };

  const rows = document.querySelectorAll('table.eK4R0e tr.y0skZc, tr.y0skZc');
  for (const row of rows) {
    const txt = row.textContent.trim().toLowerCase();
    let key = null;
    for (const [dayPart, abbr] of Object.entries(dayMap)) {
      if (txt.startsWith(dayPart)) { key = abbr; break; }
    }
    if (!key || hours[key]) continue;
    const allP = [...txt.matchAll(/(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})/g)];
    if (/atendimento\s*24\s*horas|aberto\s*24/i.test(txt)) {
      hours[key] = '00:00–23:59';
    } else if (/fechado|closed/i.test(txt)) {
      hours[key] = 'Fechado';
    } else if (allP.length >= 2) {
      hours[key] = allP.map((p) => p[1] + '–' + p[2]).join(' / ');
    } else if (allP.length === 1) {
      hours[key] = allP[0][1] + '–' + allP[0][2];
    }
  }

  const hourBtns = document.querySelectorAll('div.OMl5r[jsaction*="openhours"], div[jsaction*="openhours"] button');
  for (const btn of hourBtns) {
    const val = btn.getAttribute('data-value') || '';
    const m = val.match(/^([^,]+),\s*(.+)$/);
    if (!m) continue;
    const key = dayMap[m[1].trim().toLowerCase()];
    if (!key || hours[key]) continue;
    const rawHrs = m[2].trim();
    if (/atendimento\s*24\s*horas|aberto\s*24/i.test(rawHrs)) {
      hours[key] = '00:00–23:59';
    } else if (/fechado|closed/i.test(rawHrs)) {
      hours[key] = 'Fechado';
    } else {
      const allP = [...rawHrs.matchAll(/(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})/g)];
      if (allP.length >= 2) hours[key] = allP.map((p) => p[1] + '–' + p[2]).join(' / ');
      else if (allP.length === 1) hours[key] = allP[0][1] + '–' + allP[0][2];
    }
  }

  if (Object.keys(hours).length < 3) {
    const hoursContainer = document.querySelector('div.OqCZI, div[jsaction*="openhours"]');
    if (hoursContainer) {
      const liRows = hoursContainer.querySelectorAll('li, tr');
      for (const row of liRows) {
        const txt = row.textContent.trim().toLowerCase();
        let key = null;
        for (const [dayPart, abbr] of Object.entries(dayMap)) {
          if (txt.startsWith(dayPart)) { key = abbr; break; }
        }
        if (!key || hours[key]) continue;
        const allP = [...txt.matchAll(/(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})/g)];
        if (/atendimento\s*24\s*horas|aberto\s*24/i.test(txt)) {
          hours[key] = '00:00–23:59';
        } else if (/fechado|closed/i.test(txt)) {
          hours[key] = 'Fechado';
        } else if (allP.length >= 2) {
          hours[key] = allP.map((p) => p[1] + '–' + p[2]).join(' / ');
        } else if (allP.length === 1) {
          hours[key] = allP[0][1] + '–' + allP[0][2];
        }
      }
    }
  }

  const openEl = document.querySelector('[class*="ZjTjCd"], [class*="o0Svhf"]');
  if (openEl) {
    const txt = openEl.textContent.trim();
    if (txt) hours.status_atual = txt.slice(0, 80);
    hours.aberto_agora = !/fechado/i.test(txt);
  }

  return hours;
};
