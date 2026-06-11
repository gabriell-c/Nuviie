/* global self */
var NuviieInstagramMap = self.NuviieInstagramMap || {};

const SITE_TYPE_PATTERNS = [
  ['instagram', /instagram\.com\//i],
  ['whatsapp', /(?:wa\.me|api\.whatsapp\.com|chat\.whatsapp\.com)/i],
  ['facebook', /(?:facebook\.com|fb\.com|fb\.me)\//i],
  ['youtube', /youtube\.com\//i],
  ['linkedin', /linkedin\.com\//i],
  ['linktree', /(?:linktr\.ee|linkinbio\.|bio\.site|beacons\.ai|linky\.bio|milkshake\.app)/i],
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
  const m = bio.match(/\(?\d{2}\)?\s?(?:9\s?\d{4}|\d{4})[-\s]?\d{4}/);
  return m ? m[0] : null;
};

NuviieInstagramMap.extractAddressFromBio = (bio) => {
  if (!bio) return null;
  const m = bio.match(
    /((?:Av\.|Avenida |Rua |Rodovia |Rod\. |Alameda |Al\. |Travessa |Trav\. |Praça )[^\n]{8,200}?\d{5}-?\d{3})/i,
  );
  return m ? m[1].trim() : null;
};

NuviieInstagramMap.extractPhoneFromUrl = (url) => {
  if (!url) return null;
  const m = String(url).match(/(?:wa\.me|phone=|phone%3D|send\?phone=)[+/]?(\d{10,15})/i);
  return m ? m[1] : null;
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
  if (raw.is_business_account) parts.push('Conta comercial');
  if (raw.is_private) parts.push('Perfil privado');
  if (raw.business_email || raw.public_email) {
    parts.push(`Email: ${raw.business_email || raw.public_email}`);
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
  if (!phoneRaw) phoneRaw = NuviieInstagramMap.extractPhoneFromBio(raw.biography);

  const bioLinks = NuviieInstagramMap.extractLinksFromBio(raw.biography);

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
  if (normalized && !phoneRaw) {
    phoneRaw = NuviieInstagramMap.formatPhoneBr(normalized);
  }
  if (!phoneRaw && normalized) {
    phoneRaw = NuviieInstagramMap.formatPhoneBr(normalized);
  }

  if (!ctx.facebook && bioLinks.facebook) ctx.facebook = bioLinks.facebook;
  if (!ctx.youtube && bioLinks.youtube) ctx.youtube = bioLinks.youtube;
  if (!ctx.twitter && bioLinks.twitter) ctx.twitter = bioLinks.twitter;
  if (!ctx.linkedin && bioLinks.linkedin) ctx.linkedin = bioLinks.linkedin;

  const profilePic = raw.profile_pic_url_hd || raw.profile_pic_url || null;
  let category = raw.business_category_name || raw.category_name || niche || '';
  if (String(category).toLowerCase() === 'none') category = niche || '';
  let address = raw.business_address || NuviieInstagramMap.extractAddressFromBio(raw.biography) || null;
  const instagramUrl = `https://www.instagram.com/${handle}/`;

  return {
    name,
    category: String(category).trim(),
    city: city || '',
    phone_number: phoneRaw,
    normalized_phone: normalized,
    website: ctx.website,
    website_detected_type: ctx.website_detected_type,
    instagram: ctx.instagram,
    facebook: ctx.facebook,
    youtube: ctx.youtube,
    twitter: ctx.twitter,
    linkedin: ctx.linkedin,
    bio: NuviieInstagramMap.buildBio(raw),
    address,
    maps_url: instagramUrl,
    profile_picture_url: profilePic,
    profile_picture_data: raw.profile_picture_data || null,
    total_photos: raw.post_count != null ? Number(raw.post_count) : null,
    amenities: NuviieInstagramMap.buildAmenities(raw, handle),
    source: 'instagram',
    status: 'novo',
    is_verified: !!raw.is_verified,
  };
};

self.NuviieInstagramMap = NuviieInstagramMap;
