/* global NuviieMaps */
window.NuviieMaps = window.NuviieMaps || {};

NuviieMaps.sleep = (ms) => new Promise((r) => setTimeout(r, ms));

NuviieMaps.randomDelay = (minMs, maxMs) => {
  const ms = minMs + Math.random() * (maxMs - minMs);
  return NuviieMaps.sleep(ms);
};

NuviieMaps.basePlaceUrl = (href) => {
  if (!href) return '';
  try {
    const u = new URL(href, window.location.origin);
    return u.pathname.split('?')[0];
  } catch {
    return href.split('?')[0];
  }
};

NuviieMaps.BAD_NAMES = new Set([
  'horários', 'avaliações', 'sobre', 'visão geral', 'visao geral',
  'horarios', 'avaliacoes', 'servicos', 'serviços', 'fotos',
  'produtos', 'menu', 'reservar', 'ligar',
]);

NuviieMaps.isValidPlaceName = (name) => {
  if (!name || name.length < 2) return false;
  return !NuviieMaps.BAD_NAMES.has(name.toLowerCase().trim());
};

NuviieMaps.nameFromUrl = (url) => {
  try {
    const m = url.match(/\/maps\/place\/([^/@]+)/);
    if (!m) return null;
    const decoded = decodeURIComponent(m[1].replace(/\+/g, ' ')).trim();
    return NuviieMaps.isValidPlaceName(decoded) ? decoded : null;
  } catch {
    return null;
  }
};

NuviieMaps.normalizePhone = (phone) => {
  if (!phone) return null;
  let digits = String(phone).replace(/\D/g, '');
  if (!digits) return null;
  if (digits.startsWith('55') && digits.length > 12) digits = digits.slice(2);
  if (digits.length < 8) return null;
  if (digits.length <= 11) digits = '55' + digits;
  return digits;
};

NuviieMaps.detectCityFromPage = () => {
  const url = window.location.href;
  const qMatch = url.match(/\/search\/([^/@?]+)/);
  if (qMatch) {
    const q = decodeURIComponent(qMatch[1].replace(/\+/g, ' '));
    const parts = q.split(/\s+/);
    if (parts.length >= 2) return parts.slice(-2).join(' ');
    return q;
  }
  return '';
};

NuviieMaps.collectPlaceLinks = () => {
  const seen = new Set();
  const links = [];
  document.querySelectorAll('a[href*="/maps/place/"]').forEach((a) => {
    const href = a.href || a.getAttribute('href') || '';
    const base = NuviieMaps.basePlaceUrl(href);
    if (!base || seen.has(base)) return;
    seen.add(base);
    links.push({ href, base, element: a });
  });
  return links;
};
