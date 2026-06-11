(function initNuviieGoogleDiscover() {
  if (window.NuviieGoogleDiscover?.__loaded) return;

  const NS = window.NuviieGoogleDiscover || {};
  window.NuviieGoogleDiscover = NS;
  NS.__loaded = true;

  const IG_RESERVED_PATHS = new Set([
    'p', 'reel', 'reels', 'explore', 'stories', 'tv', 'accounts',
    'tags', 'direct', 'about', 'legal', 'developer', 'nametag',
  ]);

  NS.extractHandleFromUrl = (href) => {
    if (!href) return null;
    try {
      let url = href;
      const u = new URL(href, 'https://www.google.com');
      if (u.hostname.includes('google.') && u.pathname === '/url') {
        const q = u.searchParams.get('q') || u.searchParams.get('url');
        if (q) url = q;
      }
      const parsed = new URL(url, 'https://www.instagram.com');
      if (!parsed.hostname.includes('instagram.com')) return null;
      const parts = parsed.pathname.split('/').filter(Boolean);
      if (!parts.length) return null;
      const handle = parts[0].replace(/^@/, '');
      if (IG_RESERVED_PATHS.has(handle.toLowerCase())) return null;
      if (!/^[A-Za-z0-9._]{1,30}$/.test(handle)) return null;
      return handle.toLowerCase();
    } catch {
      return null;
    }
  };

  NS.parseSerpPage = () => {
    const seen = new Set();
    const handles = [];
    document.querySelectorAll('a[href*="instagram.com"]').forEach((a) => {
      const h = NS.extractHandleFromUrl(a.href || a.getAttribute('href') || '');
      if (h && !seen.has(h)) {
        seen.add(h);
        handles.push(h);
      }
    });
    return handles;
  };

  NS.detectCaptcha = () => {
    const body = (document.body?.innerText || '').toLowerCase();
    if (body.includes('unusual traffic') || body.includes('tráfego incomum')) return true;
    if (document.querySelector('form#captcha-form, #recaptcha, .g-recaptcha, iframe[src*="recaptcha"]')) {
      return true;
    }
    return false;
  };

})();
