/* global self */
var NuviieInstagramMap = self.NuviieInstagramMap || {};

const SITE_TYPE_PATTERNS = [
  ['instagram', /instagram\.com\//i],
  ['whatsapp', /(?:wa\.me|api\.whatsapp\.com|chat\.whatsapp\.com)/i],
  ['facebook', /(?:facebook\.com|fb\.com|fb\.me)\//i],
  ['youtube', /youtube\.com\//i],
  ['linkedin', /linkedin\.com\//i],
  ['linktree', /(?:linktr\.ee|linkinbio\.|bio\.site|beacons\.ai|linky\.bio|milkshake\.app|bit\.ly|bitly\.com|tinyurl\.com|goo\.gl|t\.co)/i],
  ['other_social', /(?:tiktok\.com|twitter\.com|x\.com|snapchat\.com|pinterest\.com|threads\.net)/i],
];

NuviieInstagramMap.detectWebsiteType = (url) => {
  if (!url) return 'website';
  for (const [typeName, pattern] of SITE_TYPE_PATTERNS) {
    if (pattern.test(url)) return typeName;
  }
  return 'website';
};

NuviieInstagramMap.normalizePhone = (phone) => {
  if (!phone) return null;
  let digits = String(phone).replace(/\D/g, '');
  if (!digits) return null;
  if (digits.startsWith('55') && digits.length > 12) digits = digits.slice(2);
  if (digits.length < 8) return null;
  if (digits.length <= 11) digits = `55${digits}`;
  return digits;
};

NuviieInstagramMap.formatPhoneBr = (normalized) => {
  if (!normalized || normalized.length < 12) return null;
  const d = normalized.startsWith('55') ? normalized.slice(2) : normalized;
  if (d.length === 11) return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
  if (d.length === 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  return normalized;
};

NuviieInstagramMap.extractPhoneFromBio = (bio) => {
  if (!bio) return null;
  const text = String(bio);

  const labeled = text.match(
    /(?:tel(?:efone)?|fone|cel(?:ular)?|whats(?:app)?|zap|contato|📞|☎️?)[:\s]*([+\d\s().\-]{10,24})/i,
  );
  if (labeled) {
    const candidate = labeled[1].trim();
    if (candidate.replace(/\D/g, '').length >= 10) return candidate;
  }

  const wa = text.match(/wa\.me\/(\d{10,15})/i);
  if (wa) return wa[1];

  const patterns = [
    /\+55\s*\(?\d{2}\)?\s*(?:9\s?\d{4}|\d{4})[-\s]?\d{4}/,
    /\(?\d{2}\)?\s*(?:9\s?\d{4}|\d{4})[-\s]?\d{4}/,
    /\b(\d{2})\s*(?:9\s?\d{4}|\d{4})[-\s]?(\d{4})\b/,
  ];
  for (const re of patterns) {
    const m = text.match(re);
    if (m) return m[0].trim();
  }
  return null;
};

NuviieInstagramMap.extractEmailFromBio = (bio) => {
  if (!bio) return null;
  const text = String(bio);
  const matches = text.match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g);
  if (!matches || !matches.length) return null;
  for (const raw of matches) {
    const email = raw.trim().toLowerCase().replace(/[.,;]+$/, '');
    // Ignora handles/CDNs que não são e-mail de contato.
    if (/\.(png|jpg|jpeg|gif|webp)$/i.test(email)) continue;
    return email;
  }
  return null;
};

NuviieInstagramMap.computeEngagementRate = (raw) => {
  const followers = Number(raw && raw.follower_count);
  if (!followers || followers <= 0) return null;
  const posts = (raw.recent_posts || []).concat(raw.recent_reels || []);
  const sample = posts
    .filter((p) => p && (p.like_count != null || p.comment_count != null))
    .slice(0, 12);
  if (!sample.length) return null;
  let sum = 0;
  for (const p of sample) {
    sum += (Number(p.like_count) || 0) + (Number(p.comment_count) || 0);
  }
  const avg = sum / sample.length;
  return Math.round((avg / followers) * 10000) / 100;
};

NuviieInstagramMap.extractAddressFromBio = (bio) => {
  if (!bio) return null;
  const text = String(bio).trim();

  const labeled = text.match(
    /(?:📍|Endere[cç]o|Local|Localiza[cç][aã]o|Onde estamos)[:\s\-–—]*([^\n]{10,250})/i,
  );
  if (labeled) {
    const addr = labeled[1].trim().replace(/^[\-–—]\s*/, '');
    if (addr.length >= 10) return addr;
  }

  const withCep = text.match(
    /((?:Av\.|Avenida |Rua |Rodovia |Rod\. |Alameda |Al\. |Travessa |Trav\. |Pra[cç]a )[^\n]{8,200}?\d{5}-?\d{3})/i,
  );
  if (withCep) return withCep[1].trim();

  const streetNum = text.match(
    /((?:Av\.?|Avenida|Rua|R\.|Alameda|Travessa|Pra[cç]a|Rod\.?|Estrada)\s+[^\n,]{2,80},?\s*\d{1,6}(?:\s*[-–—]\s*[^\n]{3,80})?)/i,
  );
  if (streetNum) return streetNum[1].trim();

  return null;
};

NuviieInstagramMap.extractCityFromBio = (bio) => {
  if (!bio) return null;
  const text = String(bio);
  const ufMatch = text.match(
    /(?:,\s*|\-\s*|\/\s*)([A-ZÀ-Ú][a-zà-ú]+(?:\s+(?:de|do|da|dos|das)\s+)?[A-ZÀ-Úa-zà-ú]+(?:\s+[A-ZÀ-Úa-zà-ú]+)?)\s*[-\/]\s*(SP|MG|RJ|PR|RS|SC|BA|GO|PE|CE|DF|ES|AM|PA|MT|MS|RN|PB|AL|SE|PI|MA|TO|RO|AC|AP|RR)/i,
  );
  if (ufMatch) return ufMatch[1].trim();
  return null;
};

NuviieInstagramMap.normalizeBioTimeRange = (raw) => {
  if (!raw) return null;
  const t = String(raw).trim();
  if (/fechado|closed/i.test(t)) return 'Fechado';
  if (/\b24\s*h|\b24\s*horas|atendimento\s*24/i.test(t)) return '00:00–23:59';

  const ranges = [...t.matchAll(/(\d{1,2})(?:[:h](\d{2}))?\s*[-–àas]+\s*(\d{1,2})(?:[:h](\d{2}))?/gi)];
  if (!ranges.length) return null;

  const fmt = (h, m) => `${String(h).padStart(2, '0')}:${String(m || 0).padStart(2, '0')}`;
  if (ranges.length >= 2) {
    return ranges.map((r) => `${fmt(r[1], r[2])}–${fmt(r[3], r[4])}`).join(' / ');
  }
  const r = ranges[0];
  return `${fmt(r[1], r[2])}–${fmt(r[3], r[4])}`;
};

NuviieInstagramMap.extractHoursFromBio = (bio) => {
  if (!bio) return null;
  const text = String(bio).replace(/\r/g, '');
  const hours = {};

  const dayKeyMap = [
    { key: 'seg', re: /seg(?:unda)?(?:[\-\s]?feira)?/i },
    { key: 'ter', re: /ter[cç]a(?:[\-\s]?feira)?/i },
    { key: 'qua', re: /quarta(?:[\-\s]?feira)?/i },
    { key: 'qui', re: /quinta(?:[\-\s]?feira)?/i },
    { key: 'sex', re: /sexta(?:[\-\s]?feira)?/i },
    { key: 'sab', re: /s[aá]bado/i },
    { key: 'dom', re: /domingo/i },
  ];

  const resolveDayKey = (fragment) => {
    for (const { key, re } of dayKeyMap) {
      if (re.test(fragment)) return key;
    }
    return null;
  };

  const weekdayOrder = ['seg', 'ter', 'qua', 'qui', 'sex', 'sab', 'dom'];

  if (/\b(?:24\s*h|24\s*horas|aberto\s*24|atendimento\s*24)\b/i.test(text)) {
    weekdayOrder.forEach((d) => { hours[d] = '00:00–23:59'; });
    hours.status_atual = 'Aberto 24 horas';
    return hours;
  }

  const lines = text.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.length < 4) continue;

    const perDay = trimmed.match(
      /^((?:seg(?:unda)?|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo)[^\n:]{0,20})[:\s\-–]+(.+)$/i,
    );
    if (perDay) {
      const dayKey = resolveDayKey(perDay[1]);
      const slot = NuviieInstagramMap.normalizeBioTimeRange(perDay[2]);
      if (dayKey && slot) hours[dayKey] = slot;
      continue;
    }

    const rangeLine = trimmed.match(
      /(seg(?:unda)?(?:\s*[-–a]\s*(?:sex(?:ta)?|dom(?:ingo)?)|\s*[-–]\s*sex))[:\s\-–]*(.+)/i,
    );
    if (rangeLine) {
      const slot = NuviieInstagramMap.normalizeBioTimeRange(rangeLine[2]);
      if (slot) {
        const endMatch = rangeLine[1].match(/dom/i) ? 'dom' : 'sex';
        const endIdx = weekdayOrder.indexOf(endMatch);
        weekdayOrder.slice(0, endIdx + 1).forEach((d) => { hours[d] = slot; });
      }
    }
  }

  const horarioBlock = text.match(
    /(?:hor[aá]rio|funcionamento|atendimento|🕐|⏰)[:\s\-–]*([^\n]{6,120})/i,
  );
  if (horarioBlock && Object.keys(hours).length === 0) {
    const block = horarioBlock[1];
    const rangeAll = block.match(
      /(seg(?:unda)?(?:\s*[-–a]\s*(?:sex(?:ta)?|s[aá]b(?:ado)?|dom(?:ingo)?)))[\s:,\-–]*(\d{1,2}(?:[:h]\d{2})?\s*[-–àas]+\s*\d{1,2}(?:[:h]\d{2})?|fechado|24\s*h[^\s]*)/i,
    );
    if (rangeAll) {
      const slot = NuviieInstagramMap.normalizeBioTimeRange(rangeAll[2]);
      const endMatch = rangeAll[1].match(/dom/i) ? 'dom'
        : rangeAll[1].match(/s[aá]b/i) ? 'sab' : 'sex';
      const endIdx = weekdayOrder.indexOf(endMatch);
      if (slot && endIdx >= 0) {
        weekdayOrder.slice(0, endIdx + 1).forEach((d) => { hours[d] = slot; });
      }
    } else {
      const slot = NuviieInstagramMap.normalizeBioTimeRange(block);
      if (slot) weekdayOrder.slice(0, 5).forEach((d) => { hours[d] = slot; });
    }
  }

  const openNow = text.match(/\b(aberto|fechado)\b(?:\s*agora)?/i);
  if (openNow) hours.status_atual = openNow[0].trim();

  return Object.keys(hours).filter((k) => k !== 'status_atual').length ? hours : null;
};

NuviieInstagramMap.extractPhoneFromUrl = (url) => {
  if (!url) return null;
  const m = String(url).match(/(?:wa\.me|phone=|phone%3D|send\?phone=)[+/]?(\d{10,15})/i);
  return m ? m[1] : null;
};

NuviieInstagramMap.hasRealWebsite = (lead) => {
  if (!lead) return false;
  return !!(lead.website && lead.website_detected_type === 'website');
};

NuviieInstagramMap.hasBioLink = (lead) => {
  if (!lead) return false;
  if (lead.website) return true;
  if (lead.website_detected_type && lead.website_detected_type !== 'website') return true;
  if (lead.normalized_phone) return true;
  const amenities = lead.amenities;
  if (amenities && typeof amenities === 'object' && !Array.isArray(amenities)) {
    if (Array.isArray(amenities.bio_links) && amenities.bio_links.length) return true;
  }
  const bio = lead.bio || '';
  if (/https?:\/\//i.test(bio)) return true;
  return false;
};

NuviieInstagramMap.extractLinksFromBio = (bio) => {
  const out = { facebook: null, youtube: null, twitter: null, linkedin: null, whatsapp: null };
  if (!bio) return out;
  const urls = bio.match(/https?:\/\/[^\s<>"']+/gi) || [];
  for (const url of urls) {
    const type = NuviieInstagramMap.detectWebsiteType(url);
    if (type === 'facebook' && !out.facebook) out.facebook = url;
    else if (type === 'youtube' && !out.youtube) out.youtube = url;
    else if (type === 'other_social' && /tiktok|twitter|x\.com/i.test(url) && !out.twitter) {
      out.twitter = url;
    } else if (type === 'linkedin' && !out.linkedin) out.linkedin = url;
    else if (type === 'whatsapp' && !out.whatsapp) out.whatsapp = url;
  }
  return out;
};

NuviieInstagramMap.formatPostDate = (unixTs) => {
  if (!unixTs) return null;
  try {
    return new Date(Number(unixTs) * 1000).toLocaleDateString('pt-BR');
  } catch {
    return null;
  }
};

NuviieInstagramMap.buildBio = (raw) => {
  const parts = [];
  if (raw.biography) parts.push(String(raw.biography).trim());

  if (raw.latest_post) {
    const lp = raw.latest_post;
    const d = NuviieInstagramMap.formatPostDate(lp.taken_at);
    const cap = (lp.caption || '').trim();
    const preview = cap.length > 180 ? `${cap.slice(0, 180)}…` : cap;
    parts.push(`Última publicação${d ? ` (${d})` : ''}: ${preview || `[${lp.type}]`}`);
    if (lp.permalink) parts.push(`Link: ${lp.permalink}`);
  } else if (raw.latest_post_at) {
    const d = NuviieInstagramMap.formatPostDate(raw.latest_post_at);
    if (d) parts.push(`Última postagem: ${d}`);
  }

  if (raw.follower_count != null) {
    parts.push(`Seguidores: ${Number(raw.follower_count).toLocaleString('pt-BR')}`);
  }
  if (raw.following_count != null) {
    parts.push(`Seguindo: ${Number(raw.following_count).toLocaleString('pt-BR')}`);
  }
  if (raw.post_count != null) {
    parts.push(`Publicações: ${Number(raw.post_count).toLocaleString('pt-BR')}`);
  }
  if (raw.reels_count != null) {
    parts.push(`Reels: ${Number(raw.reels_count).toLocaleString('pt-BR')}`);
  }
  if (raw.engagement_rate != null) {
    parts.push(`Engajamento médio: ${raw.engagement_rate}%`);
  }
  if (raw.is_business_account) parts.push('Conta comercial');
  if (raw.is_private) parts.push('Perfil privado');
  if (raw.business_email || raw.public_email) {
    parts.push(`Email: ${raw.business_email || raw.public_email}`);
  }
  if (raw.whatsapp_number || raw.is_whatsapp_linked) {
    parts.push(`WhatsApp vinculado${raw.whatsapp_number ? `: ${raw.whatsapp_number}` : ''}`);
  }
  if (raw.connected_fb_page) {
    parts.push(`Facebook conectado: ${raw.connected_fb_page}`);
  }
  const cat = raw.business_category_name || raw.category_name;
  if (cat && String(cat).toLowerCase() !== 'none') {
    parts.push(`Categoria IG: ${cat}`);
  }
  return parts.join('\n').slice(0, 2000);
};

NuviieInstagramMap.buildAmenities = (raw, handle) => {
  const amenities = {
    ig_user_id: raw.id || null,
    instagram_url: `https://www.instagram.com/${handle}/`,
    follower_count: raw.follower_count ?? null,
    following_count: raw.following_count ?? null,
    post_count: raw.post_count ?? null,
    latest_post_at: raw.latest_post_at ?? null,
    reels_count: raw.reels_count ?? null,
    is_private: !!raw.is_private,
    is_business_account: !!raw.is_business_account,
  };
  if (raw.is_professional_account != null) amenities.is_professional_account = !!raw.is_professional_account;
  if (raw.account_type != null) amenities.account_type = raw.account_type;
  if (raw.category_id) amenities.category_id = raw.category_id;
  if (raw.pronouns) amenities.pronouns = raw.pronouns;
  if (raw.whatsapp_number) amenities.whatsapp_number = raw.whatsapp_number;
  if (raw.is_whatsapp_linked != null) amenities.is_whatsapp_linked = !!raw.is_whatsapp_linked;
  if (raw.business_contact_method) amenities.business_contact_method = raw.business_contact_method;
  if (raw.public_email || raw.business_email) amenities.email = raw.public_email || raw.business_email;
  if (raw.zip_code) amenities.zip_code = raw.zip_code;
  if (raw.latitude != null) amenities.latitude = raw.latitude;
  if (raw.longitude != null) amenities.longitude = raw.longitude;
  if (raw.engagement_rate != null) amenities.engagement_rate = raw.engagement_rate;
  if (raw.bio_links_parsed?.length) {
    amenities.bio_links = raw.bio_links_parsed;
  }
  if (raw.connected_fb_page) {
    amenities.connected_fb_page = raw.connected_fb_page;
  }
  if (raw.latest_post) {
    amenities.latest_post = raw.latest_post;
  }
  if (raw.recent_posts?.length) {
    amenities.recent_posts = raw.recent_posts;
  }
  if (raw.recent_reels?.length) {
    amenities.recent_reels = raw.recent_reels;
  }
  return amenities;
};

NuviieInstagramMap.decodeBioLinkUrl = (url) => {
  if (!url) return null;
  let clean = String(url).trim();
  if (/l\.instagram\.com/i.test(clean)) {
    try {
      const parsed = new URL(clean);
      const target = parsed.searchParams.get('u');
      if (target) return decodeURIComponent(target);
    } catch {
      /* ignore */
    }
  }
  return clean;
};

NuviieInstagramMap.cleanSocialUrl = (url) => {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    parsed.search = '';
    parsed.hash = '';
    return parsed.toString().replace(/\/$/, '');
  } catch {
    return String(url).split('?')[0].split('#')[0];
  }
};

NuviieInstagramMap.applyExternalUrl = (externalUrl, ctx, options = {}) => {
  if (!externalUrl) return;
  const decoded = NuviieInstagramMap.decodeBioLinkUrl(externalUrl);
  if (!decoded) return;
  const websiteType = NuviieInstagramMap.detectWebsiteType(decoded);
  const primary = options.primary !== false;

  if (websiteType === 'website') {
    if (!ctx.website) {
      ctx.website = decoded;
      ctx.website_detected_type = 'website';
    }
  } else if (websiteType === 'linktree') {
    if (!ctx.website || primary) {
      if (!ctx.website) ctx.website = decoded;
      if (!ctx.website_detected_type || primary) ctx.website_detected_type = 'linktree';
    }
  } else if (websiteType === 'instagram') {
    const m = decoded.match(/instagram\.com\/([A-Za-z0-9._]{1,30})/i);
    if (m) ctx.instagram = `@${m[1].replace(/\/$/, '')}`;
  } else if (websiteType === 'whatsapp') {
    const m = decoded.match(/(?:wa\.me|phone=|phone%3D)[+/]?(\d{10,15})/);
    if (m && !ctx.normalized) ctx.normalized = m[1];
  } else if (websiteType === 'facebook') {
    ctx.facebook = ctx.facebook || NuviieInstagramMap.cleanSocialUrl(decoded);
  } else if (websiteType === 'youtube') {
    ctx.youtube = ctx.youtube || NuviieInstagramMap.cleanSocialUrl(decoded);
  } else if (websiteType === 'linkedin') {
    ctx.linkedin = ctx.linkedin || NuviieInstagramMap.cleanSocialUrl(decoded);
  } else if (websiteType === 'other_social') {
    ctx.twitter = ctx.twitter || NuviieInstagramMap.cleanSocialUrl(decoded);
  }
};

NuviieInstagramMap.mapInstagramToLead = (raw, { city, niche, handle: handleHint }) => {
  if (!raw) return null;
  const handle = (raw.username || raw.handle || handleHint || '').replace(/^@/, '').toLowerCase();
  if (!handle) return null;

  const name = (raw.full_name || raw.name || handle.replace(/[._]/g, ' ')).trim();
  if (!name) return null;

  const ctx = {
    website: null,
    website_detected_type: null,
    instagram: `@${handle}`,
    facebook: null,
    youtube: null,
    twitter: null,
    linkedin: null,
    normalized: null,
  };

  NuviieInstagramMap.applyExternalUrl(raw.external_url, ctx, { primary: true });

  if (Array.isArray(raw.bio_links_parsed)) {
    for (const link of raw.bio_links_parsed) {
      NuviieInstagramMap.applyExternalUrl(link, ctx, { primary: false });
    }
  }

  if (raw.connected_fb_page) {
    const fbId = typeof raw.connected_fb_page === 'object'
      ? (raw.connected_fb_page.id || raw.connected_fb_page.page_id)
      : raw.connected_fb_page;
    if (fbId && /^\d+$/.test(String(fbId))) {
      NuviieInstagramMap.applyExternalUrl(`https://www.facebook.com/${fbId}`, ctx, { primary: false });
    }
  }

  let phoneRaw = raw.business_phone_number || raw.public_phone_number || raw.contact_phone_number || null;
  const bioText = raw.biography || '';
  if (!phoneRaw) phoneRaw = NuviieInstagramMap.extractPhoneFromBio(bioText);

  const bioLinks = NuviieInstagramMap.extractLinksFromBio(bioText);

  let normalized = NuviieInstagramMap.normalizePhone(phoneRaw);
  if (ctx.normalized && !normalized) {
    normalized = NuviieInstagramMap.normalizePhone(ctx.normalized) || ctx.normalized;
  }
  if (bioLinks.whatsapp && !normalized) {
    const fromWa = NuviieInstagramMap.extractPhoneFromUrl(bioLinks.whatsapp);
    if (fromWa) normalized = NuviieInstagramMap.normalizePhone(fromWa) || fromWa;
  }
  if (Array.isArray(raw.bio_links_parsed)) {
    for (const link of raw.bio_links_parsed) {
      if (normalized) break;
      if (NuviieInstagramMap.detectWebsiteType(link) === 'whatsapp') {
        const fromWa = NuviieInstagramMap.extractPhoneFromUrl(link);
        if (fromWa) normalized = NuviieInstagramMap.normalizePhone(fromWa) || fromWa;
      }
    }
  }
  if (!normalized && raw.whatsapp_number) {
    normalized = NuviieInstagramMap.normalizePhone(raw.whatsapp_number) || normalized;
  }
  if (!phoneRaw && normalized) {
    phoneRaw = NuviieInstagramMap.formatPhoneBr(normalized);
  }

  if (!ctx.facebook && raw.connected_fb_page) {
    const fb = String(raw.connected_fb_page).trim();
    if (/^\d+$/.test(fb)) {
      ctx.facebook = `https://www.facebook.com/${fb}`;
    } else if (fb && !/\s/.test(fb)) {
      ctx.facebook = `https://www.facebook.com/${fb.replace(/^@/, '')}`;
    }
  }
  if (!ctx.facebook && raw.fbid && /^\d+$/.test(String(raw.fbid))) {
    ctx.facebook = `https://www.facebook.com/${raw.fbid}`;
  }

  if (!ctx.facebook && bioLinks.facebook) ctx.facebook = bioLinks.facebook;
  if (!ctx.youtube && bioLinks.youtube) ctx.youtube = bioLinks.youtube;
  if (!ctx.twitter && bioLinks.twitter) ctx.twitter = bioLinks.twitter;
  if (!ctx.linkedin && bioLinks.linkedin) ctx.linkedin = bioLinks.linkedin;

  const profilePic = raw.profile_pic_url_hd || raw.profile_pic_url || null;
  let category = raw.business_category_name || raw.category_name || niche || '';
  if (String(category).toLowerCase() === 'none') category = niche || '';
  let address = raw.business_address || NuviieInstagramMap.extractAddressFromBio(bioText) || null;
  let businessHours = null;
  if (raw.business_hours && typeof raw.business_hours === 'object') {
    businessHours = raw.business_hours;
  } else if (raw.opening_hours && typeof raw.opening_hours === 'object') {
    businessHours = raw.opening_hours;
  } else {
    businessHours = NuviieInstagramMap.extractHoursFromBio(bioText);
  }
  let leadCity = city || raw.city_name || NuviieInstagramMap.extractCityFromBio(bioText) || '';
  const email = raw.public_email || raw.business_email
    || NuviieInstagramMap.extractEmailFromBio(bioText) || null;

  raw.engagement_rate = NuviieInstagramMap.computeEngagementRate(raw);

  const hasRealSite = !!(ctx.website && ctx.website_detected_type === 'website');
  const hasContact = !!(normalized || email);
  const isProfessional = !!(raw.is_business_account || raw.is_professional_account);
  let isActive = false;
  if (raw.latest_post_at) {
    const daysAgo = (Date.now() / 1000 - Number(raw.latest_post_at)) / 86400;
    isActive = daysAgo <= 60;
  }
  // Lead "quente" para uma agência: profissional/ativo, com contato e SEM site próprio.
  const isOpportunity = !hasRealSite && hasContact && (isProfessional || isActive);

  const amenities = NuviieInstagramMap.buildAmenities(raw, handle);
  amenities.has_real_site = hasRealSite;
  amenities.is_opportunity = isOpportunity;

  const instagramUrl = `https://www.instagram.com/${handle}/`;

  return {
    name,
    category: String(category).trim(),
    city: leadCity,
    phone_number: phoneRaw,
    normalized_phone: normalized,
    email,
    website: ctx.website,
    website_detected_type: ctx.website_detected_type,
    instagram: ctx.instagram,
    facebook: ctx.facebook,
    youtube: ctx.youtube,
    twitter: ctx.twitter,
    linkedin: ctx.linkedin,
    bio: NuviieInstagramMap.buildBio(raw),
    address,
    business_hours: businessHours,
    maps_url: instagramUrl,
    profile_picture_url: profilePic,
    profile_picture_data: raw.profile_picture_data || null,
    total_photos: raw.post_count != null ? Number(raw.post_count) : null,
    amenities,
    source: 'instagram',
    status: 'novo',
    is_verified: !!raw.is_verified,
  };
};

self.NuviieInstagramMap = NuviieInstagramMap;
