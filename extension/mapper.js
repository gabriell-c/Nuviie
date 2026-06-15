/* global NuviieMaps */
window.NuviieMaps = window.NuviieMaps || {};

const SITE_TYPE_PATTERNS = [
  ['instagram', /instagram\.com\//i],
  ['whatsapp', /(?:wa\.me|api\.whatsapp\.com|chat\.whatsapp\.com)/i],
  ['facebook', /(?:facebook\.com|fb\.com|fb\.me)\//i],
  ['youtube', /youtube\.com\//i],
  ['linkedin', /linkedin\.com\//i],
  ['linktree', /(?:linktr\.ee|linkinbio\.|bio\.site|beacons\.ai|linky\.bio|milkshake\.app)/i],
  ['other_social', /(?:tiktok\.com|twitter\.com|x\.com|snapchat\.com|pinterest\.com|threads\.net)/i],
];

NuviieMaps.detectWebsiteType = (url) => {
  if (!url) return 'website';
  for (const [typeName, pattern] of SITE_TYPE_PATTERNS) {
    if (pattern.test(url)) return typeName;
  }
  return 'website';
};

NuviieMaps.mergeHours = (fromExtract, fromHours) => {
  const merged = { ...(fromExtract || {}) };
  if (fromHours) {
    Object.entries(fromHours).forEach(([k, v]) => {
      if (v && (!merged[k] || k === 'status_atual' || k === 'aberto_agora')) merged[k] = v;
    });
  }
  return merged;
};

NuviieMaps.mergeAmenities = (aboutList, jsList) => {
  const seen = new Set();
  const out = [];
  [...(aboutList || []), ...(jsList || [])].forEach((item) => {
    if (item && !seen.has(item)) {
      seen.add(item);
      out.push(item);
    }
  });
  return out;
};

NuviieMaps.mapToLead = (raw, { city, niche, mapsUrl, reviews, aboutAmenities, hoursExtra }) => {
  const js = raw || {};
  let name = (js.name || '').trim();
  if (!NuviieMaps.isValidPlaceName(name)) {
    name = NuviieMaps.nameFromUrl(mapsUrl || window.location.href) || name;
  }
  if (!NuviieMaps.isValidPlaceName(name)) return null;

  let phoneRaw = js.phone || null;
  let normalized = NuviieMaps.normalizePhone(phoneRaw);
  if (js.whatsapp_link && !normalized) {
    normalized = js.whatsapp_link.startsWith('55') ? js.whatsapp_link : `55${js.whatsapp_link}`;
    if (!phoneRaw && normalized.length >= 12) {
      phoneRaw = `(${normalized.slice(2, 4)}) ${normalized.slice(4, 9)}-${normalized.slice(9)}`;
    }
  }

  let rawWebsite = js.website || null;
  let websiteType = NuviieMaps.detectWebsiteType(rawWebsite);
  let website = websiteType === 'website' ? rawWebsite : null;
  let instagram = js.instagram || null;
  let facebook = js.facebook || null;
  let youtube = js.youtube || null;
  let twitter = js.twitter || null;
  let linkedin = js.linkedin || null;

  if (!rawWebsite && js.menu && js.menu !== 'disponível') {
    const menuType = NuviieMaps.detectWebsiteType(js.menu);
    if (menuType === 'website') {
      rawWebsite = js.menu;
      websiteType = menuType;
      website = rawWebsite;
    }
  }

  if (!twitter && js.tiktok) {
    const tt = String(js.tiktok).replace(/^@/, '');
    twitter = tt.startsWith('http') ? tt : `https://www.tiktok.com/@${tt}`;
  }

  if (rawWebsite && websiteType === 'instagram') {
    const m = rawWebsite.match(/instagram\.com\/([A-Za-z0-9._]{1,50})/i);
    if (m && !instagram) instagram = `@${m[1].replace(/\/$/, '')}`;
    website = null;
  } else if (rawWebsite && websiteType === 'whatsapp') {
    const m = rawWebsite.match(/(?:wa\.me|phone=|phone%3D)[+/]?(\d{10,15})/);
    if (m && !normalized) normalized = m[1];
    website = null;
  } else if (rawWebsite && websiteType === 'facebook') {
    if (!facebook) facebook = rawWebsite;
    website = null;
  } else if (rawWebsite && websiteType === 'youtube') {
    if (!youtube) youtube = rawWebsite;
    website = null;
  } else if (rawWebsite && websiteType === 'linkedin') {
    if (!linkedin) linkedin = rawWebsite;
    website = null;
  } else if (rawWebsite && websiteType === 'other_social') {
    if (/tiktok\.com/i.test(rawWebsite) && !twitter) {
      twitter = rawWebsite;
    } else if (/(?:twitter|x)\.com/i.test(rawWebsite) && !twitter) {
      twitter = rawWebsite;
    }
    website = null;
  }

  const hours = NuviieMaps.mergeHours(js.hours, hoursExtra);
  const amenities = NuviieMaps.mergeAmenities(aboutAmenities, js.amenities);

  const mapsCanonical = mapsUrl || js.maps_url || window.location.href.split('?')[0];

  return {
    name,
    category: (js.category || niche || '').trim(),
    city: city || '',
    phone_number: phoneRaw,
    normalized_phone: normalized,
    website,
    website_detected_type: websiteType,
    instagram,
    facebook,
    youtube,
    twitter,
    linkedin,
    bio: (js.bio || '').slice(0, 800),
    address: js.address || null,
    rating: js.rating || null,
    review_count: js.review_count || 0,
    recent_reviews: reviews && reviews.length ? reviews : null,
    business_hours: Object.keys(hours).length ? hours : null,
    maps_url: mapsCanonical,
    maps_share_url: js.share_url || null,
    profile_picture_url: js.og_image || null,
    source: 'google_maps',
    status: 'novo',
    is_verified: false,
    _price_range: js.price_range || null,
    _plus_code: js.plus_code || null,
    _amenities: amenities.length ? amenities : null,
    _total_photos: js.total_photos || null,
    _latitude: js.latitude || null,
    _longitude: js.longitude || null,
    _cid: js.cid || null,
    _kgmid: js.kgmid || null,
  };
};
