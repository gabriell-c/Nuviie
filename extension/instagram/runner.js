/* global self, NuviieInstagramMap */
importScripts('instagram/map-lead.js');

const NuviieInstagramRunner = {
  state: {
    running: false,
    stopRequested: false,
    leads: [],
    progress: { current: 0, total: 0, status: 'idle', message: 'Pronto.' },
  },
  injectedScriptTabs: new Set(),
  injectPromises: new Map(),

  sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  },

  sendProgress() {
    chrome.runtime.sendMessage({
      type: 'PROGRESS',
      progress: { ...this.state.progress },
      leadsCount: this.state.leads.length,
      mode: 'instagram',
    }).catch(() => {});
    chrome.storage.local.set({
      nuviieLeads: this.state.leads,
      nuviieProgress: this.state.progress,
      nuviieMode: 'instagram',
    }).catch(() => {});
  },

  buildQueries(niche, city) {
    const n = niche.trim();
    const c = city.trim();
    if (c) {
      return [
        `site:instagram.com "${n}" "${c}"`,
        `site:instagram.com ${n} ${c}`,
      ];
    }
    return [`site:instagram.com "${n}"`];
  },

  waitTabComplete(tabId, timeoutMs = 15000) {
    return new Promise((resolve, reject) => {
      const start = Date.now();
      let settled = false;
      const finish = (fn) => {
        if (settled) return;
        settled = true;
        chrome.tabs.onUpdated.removeListener(listener);
        fn();
      };

      const listener = (id, info) => {
        if (id !== tabId || info.status !== 'complete') return;
        finish(resolve);
      };
      chrome.tabs.onUpdated.addListener(listener);

      const poll = async () => {
        if (settled) return;
        try {
          const tab = await chrome.tabs.get(tabId);
          if (tab.status === 'complete') {
            finish(resolve);
            return;
          }
        } catch (e) {
          finish(() => reject(e));
          return;
        }
        if (Date.now() - start > timeoutMs) {
          // Google Search nem sempre dispara "complete"; seguimos após timeout.
          finish(resolve);
          return;
        }
        setTimeout(poll, 400);
      };
      poll();
    });
  },

  async createInactiveTab(url) {
    const tab = await chrome.tabs.create({ url, active: false });
    await this.waitTabComplete(tab.id);
    await this.sleep(800);
    return tab;
  },

  async discoverHandles(niche, city, limit) {
    const queries = this.buildQueries(niche, city);
    const seen = new Set();
    const handles = [];
    let pageNum = 0;

    for (const query of queries) {
      if (handles.length >= limit || this.state.stopRequested) break;

      let start = 0;
      while (handles.length < limit && start <= 90 && !this.state.stopRequested) {
        pageNum += 1;
        this.state.progress = {
          current: handles.length,
          total: limit,
          status: 'running',
          message: `Google: buscando "${query}" (pág. ${pageNum})… ${handles.length} @ encontrados`,
        };
        this.sendProgress();

        const url = `https://www.google.com/search?q=${encodeURIComponent(query)}&num=10&start=${start}&hl=pt-BR`;
        let tab = null;
        try {
          tab = await this.createInactiveTab(url);
          await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            files: ['instagram/google-discover.js'],
          });

          const [{ result: captcha }] = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => window.NuviieGoogleDiscover.detectCaptcha(),
          });
          if (captcha) {
            throw new Error('Google bloqueou com CAPTCHA. Abra google.com, resolva o desafio manualmente e tente de novo.');
          }

          const [{ result: pageHandles }] = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => window.NuviieGoogleDiscover.parseSerpPage(),
          });

          if (!pageHandles?.length) break;

          const before = handles.length;
          for (const h of pageHandles) {
            if (!seen.has(h)) {
              seen.add(h);
              handles.push(h);
              if (handles.length >= limit) break;
            }
          }

          if (handles.length === before) break;
          if (pageHandles.length < 5) break;
          start += 10;
        } catch (err) {
          if (err.message?.includes('CAPTCHA')) throw err;
          console.warn('[NuviieInstagram] Erro na página Google:', err);
          break;
        } finally {
          if (tab?.id) {
            chrome.tabs.remove(tab.id).catch(() => {});
          }
        }
      }
    }

    return handles.slice(0, limit);
  },

  async ensureInstagramTab() {
    const tabs = await chrome.tabs.query({ url: ['*://www.instagram.com/*', '*://instagram.com/*'] });
    if (tabs.length) {
      const tab = tabs[0];
      if (tab.status !== 'complete') await this.waitTabComplete(tab.id);
      return tab;
    }
    return this.createInactiveTab('https://www.instagram.com/');
  },

  async ensureFetchScript(tabId, force = false) {
    if (force) {
      this.injectedScriptTabs.delete(tabId);
      this.injectPromises.delete(tabId);
    }
    if (this.injectedScriptTabs.has(tabId)) return;
    if (this.injectPromises.has(tabId)) {
      await this.injectPromises.get(tabId);
      return;
    }
    const injectPromise = chrome.scripting.executeScript({
      target: { tabId },
      files: ['instagram/fetch-profile.js'],
      world: 'MAIN',
    }).then(() => {
      this.injectedScriptTabs.add(tabId);
    }).finally(() => {
      this.injectPromises.delete(tabId);
    });
    this.injectPromises.set(tabId, injectPromise);
    await injectPromise;
  },

  async prepareInstagramTab(tabId) {
    try {
      const tab = await chrome.tabs.get(tabId);
      const onIg = tab.url && tab.url.includes('instagram.com');
      if (!onIg) {
        await chrome.tabs.update(tabId, { url: 'https://www.instagram.com/', active: false });
        await this.waitTabComplete(tabId, 25000);
        await this.sleep(1200);
      }
    } catch (e) {
      /* ignore */
    }
    await this.ensureFetchScript(tabId, true);
  },

  isValidProfileRaw(raw) {
    if (!raw || typeof raw !== 'object') return false;
    return !!(raw.username || raw.full_name || raw.biography
      || raw.follower_count != null || raw.profile_pic_url || raw.profile_pic_url_hd);
  },

  async runFetchOnTab(tabId, handle) {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId },
      world: 'MAIN',
      func: async (h) => {
        if (!window.NuviieInstagramFetch || !window.NuviieInstagramFetch.fetchProfile) {
          return null;
        }
        try {
          return await window.NuviieInstagramFetch.fetchProfile(h);
        } catch (e) {
          return null;
        }
      },
      args: [handle],
    });
    return result;
  },

  async fetchProfileOnTab(tabId, handle) {
    const maxAttempts = 3;
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      if (attempt > 0) {
        await this.ensureFetchScript(tabId, true);
        await this.sleep(1500 * attempt);
      }
      try {
        const result = await this.runFetchOnTab(tabId, handle);
        if (this.isValidProfileRaw(result)) return result;
      } catch (e) {
        console.warn('[NuviieInstagram] fetchProfile falhou:', handle, e);
        await this.ensureFetchScript(tabId, true);
      }
    }
    return null;
  },

  passesFilters(lead, filters) {
    if (filters.onlyVerified && !lead.is_verified) return false;
    if (filters.onlyWithBioLink && !NuviieInstagramMap.hasBioLink(lead)) return false;

    const websiteFilter = filters.websiteFilter || 'any';
    if (websiteFilter === 'no_real_site' && NuviieInstagramMap.hasRealWebsite(lead)) return false;
    if (websiteFilter === 'has_real_site' && !NuviieInstagramMap.hasRealWebsite(lead)) return false;

    const amenities = lead.amenities && typeof lead.amenities === 'object' ? lead.amenities : {};
    const followers = amenities.follower_count != null ? Number(amenities.follower_count) : null;
    const posts = lead.total_photos != null
      ? Number(lead.total_photos)
      : (amenities.post_count != null ? Number(amenities.post_count) : null);

    if (filters.minFollowers != null && filters.minFollowers !== '') {
      const min = Number(filters.minFollowers);
      if (followers == null || Number.isNaN(min) || followers < min) return false;
    }
    if (filters.maxFollowers != null && filters.maxFollowers !== '') {
      const max = Number(filters.maxFollowers);
      if (followers == null || Number.isNaN(max) || followers > max) return false;
    }
    if (filters.minPosts != null && filters.minPosts !== '') {
      const min = Number(filters.minPosts);
      if (posts == null || Number.isNaN(min) || posts < min) return false;
    }
    if (filters.maxPosts != null && filters.maxPosts !== '') {
      const max = Number(filters.maxPosts);
      if (posts == null || Number.isNaN(max) || posts > max) return false;
    }

    const lastPostWithin = filters.lastPostWithin || 'any';
    if (lastPostWithin !== 'any') {
      const ts = amenities.latest_post_at;
      if (ts == null) return false;
      const maxDays = { '24h': 1, '3d': 3, '7d': 7, '30d': 30 }[lastPostWithin];
      if (!maxDays) return false;
      const daysAgo = (Date.now() / 1000 - Number(ts)) / 86400;
      if (daysAgo > maxDays) return false;
    }

    return true;
  },

  formatEnrichStats(saved, filtered, failed) {
    const parts = [`${saved} extraídos`];
    if (filtered) parts.push(`${filtered} filtrados`);
    if (failed) parts.push(`${failed} falhas`);
    return parts.join(', ');
  },

  async enrichHandles(handles, options, igTabId) {
    const leads = [];
    let withPhoto = 0;
    let filtered = 0;
    let failed = 0;

    await this.prepareInstagramTab(igTabId);

    for (let i = 0; i < handles.length; i++) {
      if (this.state.stopRequested) break;

      const handle = handles[i];
      const raw = await this.fetchProfileOnTab(igTabId, handle);

      if (!raw) {
        failed += 1;
      } else {
        const lead = NuviieInstagramMap.mapInstagramToLead(raw, {
          city: options.city,
          niche: options.niche,
          handle,
        });
        if (!lead) {
          failed += 1;
        } else if (!this.passesFilters(lead, options.filters || {})) {
          filtered += 1;
        } else {
          if (lead.profile_picture_url || lead.profile_picture_data) withPhoto += 1;
          leads.push(lead);
        }
      }

      const done = i + 1;
      const stats = this.formatEnrichStats(leads.length, filtered, failed);
      this.state.progress = {
        current: done,
        total: handles.length,
        status: 'running',
        message: `Enriquecendo ${done}/${handles.length} — ${stats} (${withPhoto} com foto)`,
      };
      this.state.leads = leads;
      this.sendProgress();

      if (i + 1 < handles.length) {
        await this.sleep(800);
      }
    }

    return { leads, filtered, failed, withPhoto };
  },

  async run(options) {
    if (this.state.running) {
      return { ok: false, error: 'Extração Instagram já em andamento. Feche e reabra o popup ou clique Parar.' };
    }

    const niche = (options.niche || '').trim();
    const city = (options.city || '').trim();
    const limit = Math.max(1, parseInt(options.limit, 10) || 20);

    if (!niche) return { ok: false, error: 'Informe o nicho.' };
    if (!city) return { ok: false, error: 'Informe a cidade.' };

    this.state.running = true;
    this.state.stopRequested = false;
    this.state.leads = [];
    this.state.progress = {
      current: 0,
      total: 0,
      status: 'running',
      message: 'Buscando perfis no Google...',
    };
    this.sendProgress();

    let igTab = null;
    try {
      const handles = await this.discoverHandles(niche, city, limit);
      if (this.state.stopRequested) {
        throw new Error('STOPPED');
      }
      if (!handles.length) {
        throw new Error('Nenhum perfil encontrado no Google. Tente outro nicho ou cidade.');
      }

      this.state.progress = {
        current: 0,
        total: handles.length,
        status: 'running',
        message: `${handles.length} perfis encontrados. Enriquecendo...`,
      };
      this.sendProgress();

      igTab = await this.ensureInstagramTab();
      const enrichResult = await this.enrichHandles(handles, { ...options, city, niche }, igTab.id);
      const leads = enrichResult.leads;
      const { filtered, failed, withPhoto } = enrichResult;

      this.state.leads = leads;
      const stopped = this.state.stopRequested;
      const stats = this.formatEnrichStats(leads.length, filtered, failed);
      this.state.progress = {
        current: handles.length,
        total: handles.length,
        status: stopped ? 'stopped' : 'done',
        message: stopped
          ? `Parado. ${stats} (${withPhoto} com foto).`
          : `Concluído! ${stats} (${withPhoto} com foto).`,
      };
      this.sendProgress();

      chrome.runtime.sendMessage({
        type: 'EXTRACTION_DONE',
        leads,
        progress: this.state.progress,
        mode: 'instagram',
      }).catch(() => {});

      return { ok: true, leads, progress: this.state.progress };
    } catch (err) {
      const msg = err.message === 'STOPPED'
        ? `Parado. ${this.state.leads.length} leads extraídos.`
        : (err.message || 'Erro na extração Instagram.');
      this.state.progress = {
        current: this.state.progress.current,
        total: this.state.progress.total,
        status: err.message === 'STOPPED' ? 'stopped' : 'error',
        message: msg,
      };
      this.sendProgress();
      chrome.runtime.sendMessage({
        type: 'EXTRACTION_DONE',
        leads: this.state.leads,
        progress: this.state.progress,
        mode: 'instagram',
      }).catch(() => {});
      return { ok: false, error: msg, leads: this.state.leads };
    } finally {
      this.state.running = false;
    }
  },

  stop() {
    this.state.stopRequested = true;
  },
};

self.NuviieInstagramRunner = NuviieInstagramRunner;
