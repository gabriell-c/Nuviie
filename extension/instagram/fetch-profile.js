(function () {
  if (window.NuviieInstagramFetch && window.NuviieInstagramFetch.__loaded) {
    return;
  }

  var NS = window.NuviieInstagramFetch || {};
  window.NuviieInstagramFetch = NS;
  NS.__loaded = true;
  NS.IG_APP_ID_FALLBACK = '936619743392459';

  NS.getAppId = function () {
    var html = document.documentElement.innerHTML;
    var m = html.match(/"APP_ID"\s*:\s*"(\d+)"/) || html.match(/"appId"\s*:\s*"(\d+)"/);
    return m ? m[1] : NS.IG_APP_ID_FALLBACK;
  };

  NS.normalizePicUrl = function (url) {
    if (!url) return null;
    return String(url)
      .replace(/\\u0026/g, '&')
      .replace(/&amp;/g, '&')
      .replace(/\\\//g, '/')
      .replace(/\\"/g, '"');
  };

  NS.unescapeJsonString = function (s) {
    if (!s) return '';
    return String(s)
      .replace(/\\n/g, '\n')
      .replace(/\\u0026/g, '&')
      .replace(/&amp;/g, '&')
      .replace(/\\\//g, '/')
      .replace(/\\"/g, '"');
  };

  NS.isValidProfilePicUrl = function (url) {
    if (!url) return false;
    var u = String(url);
    if (/\/static\//.test(u)) return false;
    if (/instagram\.com\/static\//.test(u)) return false;
    if (/rsrc\.php/.test(u)) return false;
    return /fbcdn\.net|cdninstagram\.com|instagram\.com/.test(u);
  };

  NS.decodeBioLinkUrl = function (url) {
    if (!url) return null;
    var clean = NS.normalizePicUrl(NS.unescapeJsonString(String(url)));
    if (!clean) return null;
    if (/l\.instagram\.com/i.test(clean)) {
      try {
        var parsed = new URL(clean);
        var target = parsed.searchParams.get('u');
        if (target) return decodeURIComponent(target);
      } catch (e) {
        /* ignore */
      }
    }
    return clean;
  };

  NS.isBioLinkCandidate = function (url) {
    if (!url || !/^https?:\/\//i.test(url)) return false;
    var u = url.toLowerCase();
    if (/instagram\.com\/accounts\//.test(u)) return false;
    if (/instagram\.com\/legal\//.test(u)) return false;
    if (/help\.instagram\.com/.test(u)) return false;
    return /facebook\.com|fb\.com|fb\.me|linktr\.ee|linkinbio\.|bio\.site|beacons\.ai|milkshake\.app|youtube\.com|linkedin\.com|wa\.me|whatsapp\.com|tiktok\.com|twitter\.com|x\.com|threads\.net|snapchat\.com|pinterest\.com/.test(u);
  };

  NS.mergeBioLinksList = function (existing, extra) {
    var seen = {};
    var out = [];
    (existing || []).concat(extra || []).forEach(function (raw) {
      var url = NS.decodeBioLinkUrl(raw);
      if (!url || !NS.isBioLinkCandidate(url)) return;
      var key = url.replace(/[?#].*$/, '').toLowerCase();
      if (seen[key]) return;
      seen[key] = true;
      out.push(url);
    });
    return out;
  };

  NS.extractBioLinkFromObject = function (obj) {
    if (!obj || typeof obj !== 'object') return null;
    return NS.decodeBioLinkUrl(
      obj.url || obj.lynx_url || obj.link_url || obj.open_external_url || obj.webUri,
    );
  };

  NS.extractBioLinksFromHtml = function (html) {
    if (!html) return [];
    var links = [];

    function collectFromSection(section) {
      if (!section) return;
      var fieldRe = /"(?:url|lynx_url|link_url|open_external_url|webUri)"\s*:\s*"((?:\\.|[^"\\])*)"/g;
      var fm;
      while ((fm = fieldRe.exec(section)) !== null) {
        var fromField = NS.decodeBioLinkUrl(fm[1]);
        if (fromField && NS.isBioLinkCandidate(fromField)) links.push(fromField);
      }
    }

    var bioMatch = html.match(/"bio_links"\s*:\s*\[([\s\S]*?)\]\s*,/);
    if (bioMatch) collectFromSection(bioMatch[1]);

    var extMatch = html.match(/"external_url"\s*:\s*"((?:\\.|[^"\\])*)"/);
    if (extMatch) {
      var extUrl = NS.decodeBioLinkUrl(extMatch[1]);
      if (extUrl && NS.isBioLinkCandidate(extUrl)) links.push(extUrl);
    }

    var hrefRe = /href="(https?:\/\/(?:www\.)?(?:facebook\.com|fb\.com|linktr\.ee|youtube\.com|linkedin\.com|wa\.me|api\.whatsapp\.com)[^"]*)"/gi;
    var hm;
    while ((hm = hrefRe.exec(html)) !== null) {
      var fromHref = NS.decodeBioLinkUrl(hm[1]);
      if (fromHref && NS.isBioLinkCandidate(fromHref)) links.push(fromHref);
    }

    var fbPage = html.match(/"connected_fb_page"\s*:\s*"((?:\\.|[^"\\])*)"/);
    if (fbPage) {
      var fbId = NS.unescapeJsonString(fbPage[1]);
      if (/^\d+$/.test(fbId)) links.push('https://www.facebook.com/' + fbId);
    }

    return NS.mergeBioLinksList([], links);
  };

  NS.parseAddress = function (addr) {
    if (!addr) return null;
    if (typeof addr === 'string') {
      try {
        addr = JSON.parse(addr);
      } catch (e) {
        return addr.trim() || null;
      }
    }
    if (typeof addr !== 'object') return null;
    var parts = [addr.street_address, addr.city_name, addr.region_name, addr.zip_code].filter(Boolean);
    return parts.length ? parts.join(', ') : null;
  };

  NS.extractAddressFromHtml = function (html) {
    if (!html) return null;

    var street = html.match(/"street_address"\s*:\s*"((?:\\.|[^"\\])*)"/);
    if (street) {
      var city = html.match(/"city_name"\s*:\s*"((?:\\.|[^"\\])*)"/);
      var region = html.match(/"region_name"\s*:\s*"((?:\\.|[^"\\])*)"/);
      var zip = html.match(/"zip_code"\s*:\s*"((?:\\.|[^"\\])*)"/);
      var parts = [
        NS.unescapeJsonString(street[1]),
        city ? NS.unescapeJsonString(city[1]) : null,
        region ? NS.unescapeJsonString(region[1]) : null,
        zip ? NS.unescapeJsonString(zip[1]) : null,
      ].filter(Boolean);
      if (parts.length) return parts.join(', ');
    }

    var addrJson = html.match(/"business_address_json"\s*:\s*(\{[^}]*\})/);
    if (addrJson) {
      try {
        var parsed = JSON.parse(addrJson[1]);
        var fromJson = NS.parseAddress(parsed);
        if (fromJson) return fromJson;
      } catch (e) {
        /* ignore */
      }
    }

    var addrLine = html.match(
      /((?:Av\.|Avenida |Rua |Rodovia |Rod\. |Alameda |Al\. |Travessa |Trav\. |Praça )[^\s"\\][^"\\]{8,200}?\d{5}-?\d{3})/i,
    );
    if (addrLine) return NS.unescapeJsonString(addrLine[1]).trim();

    return null;
  };

  NS.extractProfilePicsFromHtml = function (html) {
    var out = { profile_pic_url: null, profile_pic_url_hd: null };
    if (!html) return out;

    var hdInfo = html.match(/"hd_profile_pic_url_info"\s*:\s*\{\s*"url"\s*:\s*"((?:\\.|[^"\\])*)"/);
    if (hdInfo) out.profile_pic_url_hd = NS.normalizePicUrl(NS.unescapeJsonString(hdInfo[1]));

    var hd = html.match(/"profile_pic_url_hd"\s*:\s*"((?:\\.|[^"\\])*)"/);
    if (hd) out.profile_pic_url_hd = out.profile_pic_url_hd || NS.normalizePicUrl(NS.unescapeJsonString(hd[1]));

    var pic = html.match(/"profile_pic_url"\s*:\s*"((?:\\.|[^"\\])*)"/);
    if (pic) out.profile_pic_url = NS.normalizePicUrl(NS.unescapeJsonString(pic[1]));

    if (!out.profile_pic_url && !out.profile_pic_url_hd) {
      var ogImage = html.match(/property="og:image"\s+content="([^"]+)"/i);
      if (ogImage) {
        var og = NS.normalizePicUrl(ogImage[1]);
        if (og && NS.isValidProfilePicUrl(og)) {
          out.profile_pic_url = og;
        }
      }
    }

    if (!out.profile_pic_url && !out.profile_pic_url_hd) {
      var imgAlt = html.match(/alt="Foto do perfil de [^"]*"[^>]*\ssrc="([^"]+)"/i)
        || html.match(/src="([^"]+)"[^>]*alt="Foto do perfil de/i);
      if (imgAlt) {
        var fromAlt = NS.normalizePicUrl(imgAlt[1]);
        if (fromAlt && NS.isValidProfilePicUrl(fromAlt)) {
          out.profile_pic_url = fromAlt;
        }
      }
    }

    if (!out.profile_pic_url && !out.profile_pic_url_hd) {
      var fbcdn = html.match(/"(https:\\\/\\\/[^"]*(?:fbcdn\.net|cdninstagram\.com)[^"]*t51\.2885-19[^"]*)"/i)
        || html.match(/(https:\/\/[^\s"']*(?:fbcdn\.net|cdninstagram\.com)[^\s"']*t51\.2885-19[^\s"']*)/i);
      if (fbcdn) {
        var fromCdn = NS.normalizePicUrl(NS.unescapeJsonString(fbcdn[1]));
        if (fromCdn && NS.isValidProfilePicUrl(fromCdn)) {
          out.profile_pic_url = fromCdn;
        }
      }
    }

    return out;
  };

  NS.fetchProfilePicViaBackground = async function (picUrl) {
    if (typeof chrome === 'undefined' || !chrome.runtime || !chrome.runtime.sendMessage) {
      return null;
    }
    try {
      var resp = await new Promise(function (resolve) {
        chrome.runtime.sendMessage({ type: 'FETCH_IMAGE', url: picUrl }, resolve);
      });
      if (resp && resp.ok && resp.dataUrl) return resp.dataUrl;
    } catch (e) {
      /* ignore */
    }
    return null;
  };

  NS.fetchProfilePicDataUrl = async function (picUrl) {
    if (!picUrl) return null;
    var clean = NS.normalizePicUrl(picUrl);
    if (!clean || !NS.isValidProfilePicUrl(clean)) return null;

    try {
      var resp = await fetch(clean, { credentials: 'include', mode: 'cors' });
      if (resp.ok) {
        var blob = await resp.blob();
        if (blob.size > 500000 || blob.size < 50) return null;
        return await new Promise(function (resolve) {
          var reader = new FileReader();
          reader.onload = function () { resolve(reader.result); };
          reader.onerror = function () { resolve(null); };
          reader.readAsDataURL(blob);
        });
      }
    } catch (e) {
      /* CORS — tenta via service worker */
    }

    return NS.fetchProfilePicViaBackground(clean);
  };

  NS.mergeHtmlIntoUser = function (user, html, handle) {
    if (!user || !html) return user;
    var parsed = NS.parseFromHtml(html, handle || user.username || '');
    var pics = NS.extractProfilePicsFromHtml(html);

    user.profile_pic_url_hd = user.profile_pic_url_hd || pics.profile_pic_url_hd || parsed.profile_pic_url_hd;
    user.profile_pic_url = user.profile_pic_url || pics.profile_pic_url || parsed.profile_pic_url || user.profile_pic_url_hd;

    if (!user.business_address) {
      user.business_address = parsed.business_address || NS.extractAddressFromHtml(html);
    }
    if (!user.biography && parsed.biography) user.biography = parsed.biography;
    if (!user.full_name && parsed.full_name) user.full_name = parsed.full_name;
    if (!user.external_url && parsed.external_url) user.external_url = parsed.external_url;
    if (!user.id && parsed.id) user.id = parsed.id;
    if (!user.post_count && parsed.post_count) user.post_count = parsed.post_count;
    if (!user.follower_count && parsed.follower_count) user.follower_count = parsed.follower_count;
    if (!user.following_count && parsed.following_count) user.following_count = parsed.following_count;
    if (!user.latest_post_at && parsed.latest_post_at) user.latest_post_at = parsed.latest_post_at;
    if (!user.category_name && parsed.category_name) user.category_name = parsed.category_name;
    if (!user.business_category_name && parsed.business_category_name) {
      user.business_category_name = parsed.business_category_name;
    }

    if (parsed.bio_links_parsed && parsed.bio_links_parsed.length) {
      user.bio_links_parsed = NS.mergeBioLinksList(user.bio_links_parsed, parsed.bio_links_parsed);
    }
    if (parsed.connected_fb_page && !user.connected_fb_page) {
      user.connected_fb_page = parsed.connected_fb_page;
    }

    return user;
  };

  NS.extractLatestPostTimestamp = function (user) {
    var edges = user && user.edge_owner_to_timeline_media && user.edge_owner_to_timeline_media.edges;
    if (edges && edges.length) {
      var ts = edges[0] && edges[0].node && edges[0].node.taken_at_timestamp;
      if (ts) return ts;
    }
    return null;
  };

  NS.enrichUserFromApi = function (user) {
    if (!user) return user;
    NS.normalizeUserId(user);

    user.profile_pic_url_hd = NS.normalizePicUrl(
      user.profile_pic_url_hd
      || (user.hd_profile_pic_url_info && user.hd_profile_pic_url_info.url)
      || user.profile_pic_url,
    );
    user.profile_pic_url = NS.normalizePicUrl(user.profile_pic_url);

    if (user.edge_followed_by && user.edge_followed_by.count != null) {
      user.follower_count = user.edge_followed_by.count;
    }
    if (user.edge_follow && user.edge_follow.count != null) {
      user.following_count = user.edge_follow.count;
    }
    if (user.edge_owner_to_timeline_media && user.edge_owner_to_timeline_media.count != null) {
      user.post_count = user.edge_owner_to_timeline_media.count;
    }
    if (user.total_clips_count != null) {
      user.reels_count = user.total_clips_count;
    }

    if (user.business_address_json && typeof user.business_address_json === 'string') {
      try {
        user.business_address_json = JSON.parse(user.business_address_json);
      } catch (e) {
        /* ignore */
      }
    }

    user.business_address = NS.parseAddress(user.business_address_json) || user.business_address;
    user.latest_post_at = NS.extractLatestPostTimestamp(user);

    if (Array.isArray(user.bio_links)) {
      user.bio_links_parsed = NS.mergeBioLinksList(
        user.bio_links_parsed,
        user.bio_links.map(function (l) { return NS.extractBioLinkFromObject(l); }).filter(Boolean),
      );
    }

    if (user.connected_fb_page && typeof user.connected_fb_page === 'object') {
      var fbUrl = user.connected_fb_page.url
        || (user.connected_fb_page.id ? 'https://www.facebook.com/' + user.connected_fb_page.id : null);
      if (fbUrl) {
        user.bio_links_parsed = NS.mergeBioLinksList(user.bio_links_parsed, [fbUrl]);
      }
    }

    return user;
  };

  NS.MEDIA_FETCH_COUNT = 24;
  NS.COMMENT_FETCH_LIMIT = 10;
  NS.COMMENT_ITEMS_LIMIT = 10;

  NS.sleep = function (ms) {
    return new Promise(function (r) { setTimeout(r, ms); });
  };

  NS.getCsrfToken = function () {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  };

  NS.apiHeaders = function (referer) {
    var headers = {
      'X-IG-App-ID': NS.getAppId(),
      'X-Requested-With': 'XMLHttpRequest',
      'X-ASBD-ID': '129477',
      'Referer': referer || 'https://www.instagram.com/',
    };
    var csrf = NS.getCsrfToken();
    if (csrf) headers['X-CSRFToken'] = csrf;
    return headers;
  };

  NS.normalizeUserId = function (user) {
    if (!user) return user;
    user.id = String(user.id || user.pk || user.profile_id || '');
    if (!user.id) user.id = null;
    return user;
  };

  NS.parseMediaItem = function (item, handle) {
    if (!item) return null;
    if (item.media && typeof item.media === 'object') {
      item = Object.assign({}, item.media, item);
    }
    var code = item.code || item.shortcode;
    if (!code) return null;
    var isReel = item.product_type === 'clips' || !!(item.clips_metadata);
    var permalink = isReel
      ? 'https://www.instagram.com/reel/' + code + '/'
      : 'https://www.instagram.com/p/' + code + '/';

    var imageUrl = null;
    var videoUrl = null;
    if (item.image_versions2 && item.image_versions2.candidates && item.image_versions2.candidates[0]) {
      imageUrl = NS.normalizePicUrl(item.image_versions2.candidates[0].url);
    }
    if (item.video_versions && item.video_versions[0]) {
      videoUrl = NS.normalizePicUrl(item.video_versions[0].url);
    }
    if (!videoUrl && item.video_url) {
      videoUrl = NS.normalizePicUrl(item.video_url);
    }
    if (!imageUrl && item.thumbnail_url) {
      imageUrl = NS.normalizePicUrl(item.thumbnail_url);
    }

    var carousel = [];
    if (item.carousel_media && item.carousel_media.length) {
      item.carousel_media.forEach(function (slide) {
        var slideImg = null;
        var slideVid = null;
        if (slide.image_versions2 && slide.image_versions2.candidates && slide.image_versions2.candidates[0]) {
          slideImg = NS.normalizePicUrl(slide.image_versions2.candidates[0].url);
        }
        if (slide.video_versions && slide.video_versions[0]) {
          slideVid = NS.normalizePicUrl(slide.video_versions[0].url);
        }
        carousel.push({
          media_type: slide.media_type === 2 ? 'video' : 'photo',
          image_url: slideImg,
          video_url: slideVid,
        });
      });
    }

    var mediaType = 'photo';
    if (isReel) mediaType = 'reel';
    else if (item.media_type === 8 || carousel.length) mediaType = 'carousel';
    else if (item.media_type === 2 || videoUrl) mediaType = 'video';

    return {
      id: String(item.pk || item.id || ''),
      shortcode: code,
      permalink: permalink,
      type: mediaType,
      taken_at: item.taken_at || item.device_timestamp || null,
      caption: (item.caption && item.caption.text) ? String(item.caption.text) : '',
      like_count: item.like_count != null ? item.like_count : null,
      comment_count: item.comment_count != null ? item.comment_count : null,
      view_count: item.view_count || item.play_count || null,
      image_url: imageUrl,
      video_url: videoUrl,
      carousel: carousel.length ? carousel : null,
      comments: [],
    };
  };

  NS.fetchMediaComments = async function (mediaId, limit) {
    if (!mediaId) return [];
    try {
      var resp = await fetch(
        'https://www.instagram.com/api/v1/media/' + mediaId + '/comments/?can_support_threading=true&permalink_enabled=false',
        { headers: NS.apiHeaders(), credentials: 'include' },
      );
      if (!resp.ok) return [];
      var data = await resp.json();
      var list = data.comments || data.items || [];
      return list.slice(0, limit || 8).map(function (c) {
        return {
          author: (c.user && c.user.username) ? '@' + c.user.username : 'Anônimo',
          text: c.text || '',
          like_count: c.comment_like_count || 0,
          created_at: c.created_at || null,
        };
      });
    } catch (e) {
      return [];
    }
  };

  NS.fetchUserFeed = async function (userId, count, referer) {
    try {
      var resp = await fetch(
        'https://www.instagram.com/api/v1/feed/user/' + userId + '/?count=' + (count || NS.MEDIA_FETCH_COUNT || 24),
        { headers: NS.apiHeaders(referer), credentials: 'include' },
      );
      if (!resp.ok) return [];
      var data = await resp.json();
      return data.items || [];
    } catch (e) {
      return [];
    }
  };

  NS.fetchUserReels = async function (userId, count, referer) {
    try {
      var resp = await fetch(
        'https://www.instagram.com/api/v1/clips/user/' + userId + '/?count=' + (count || NS.MEDIA_FETCH_COUNT || 24),
        { headers: NS.apiHeaders(referer), credentials: 'include' },
      );
      if (!resp.ok) return [];
      var data = await resp.json();
      return data.items || [];
    } catch (e) {
      return [];
    }
  };

  NS.nodeToMediaItem = function (node, handle) {
    if (!node || !node.shortcode) return null;
    var captionText = '';
    if (node.edge_media_to_caption && node.edge_media_to_caption.edges && node.edge_media_to_caption.edges[0]) {
      captionText = node.edge_media_to_caption.edges[0].node.text || '';
    } else if (typeof node.caption === 'string') {
      captionText = node.caption;
    } else if (node.caption && node.caption.text) {
      captionText = node.caption.text;
    }
    return NS.parseMediaItem({
      pk: node.id,
      id: node.id,
      code: node.shortcode,
      media_type: node.is_video ? 2 : (node.media_type || 1),
      product_type: node.product_type || 'feed',
      taken_at: node.taken_at_timestamp || node.taken_at,
      caption: { text: captionText },
      like_count: (node.edge_liked_by && node.edge_liked_by.count != null)
        ? node.edge_liked_by.count
        : node.like_count,
      comment_count: (node.edge_media_to_comment && node.edge_media_to_comment.count != null)
        ? node.edge_media_to_comment.count
        : node.comment_count,
      image_versions2: { candidates: [{ url: node.display_url || node.thumbnail_src || node.thumbnail_url }] },
      video_versions: node.video_url ? [{ url: node.video_url }] : null,
      video_url: node.video_url,
      clips_metadata: node.product_type === 'clips' ? {} : null,
    }, handle);
  };

  NS.parseTimelineFromHtml = function (html, handle) {
    if (!html) return [];
    var markers = [
      '"edge_owner_to_timeline_media"',
      '"xdt_api__v1__feed__user_timeline_graphql_connection"',
      '"xdt_api__v1__clips__user__connection_v2"',
    ];
    var items = [];
    markers.forEach(function (marker) {
      var idx = 0;
      while (idx < html.length) {
        var found = html.indexOf(marker, idx);
        if (found === -1) break;
        var edgesIdx = html.indexOf('"edges":[', found);
        if (edgesIdx === -1 || edgesIdx - found > 8000) {
          idx = found + marker.length;
          continue;
        }
        var arrStart = edgesIdx + '"edges":'.length;
        while (arrStart < html.length && html[arrStart] !== '[') arrStart++;
        var depth = 0;
        var end = arrStart;
        for (var i = arrStart; i < html.length && i < arrStart + 600000; i++) {
          if (html[i] === '[') depth++;
          else if (html[i] === ']') {
            depth--;
            if (depth === 0) { end = i + 1; break; }
          }
        }
        try {
          var edges = JSON.parse(html.slice(arrStart, end));
          edges.forEach(function (edge) {
            var p = NS.nodeToMediaItem(edge.node || edge, handle);
            if (p) items.push(p);
          });
        } catch (e) {
          /* ignore malformed chunk */
        }
        idx = found + marker.length;
      }
    });
    var seen = {};
    return items.filter(function (p) {
      if (!p.shortcode || seen[p.shortcode]) return false;
      seen[p.shortcode] = true;
      return true;
    });
  };

  NS.parseTimelineEdges = function (user, handle) {
    var edges = user && user.edge_owner_to_timeline_media && user.edge_owner_to_timeline_media.edges;
    if (!edges || !edges.length) return [];
    return edges.map(function (edge) {
      return NS.nodeToMediaItem(edge.node, handle);
    }).filter(Boolean);
  };

  NS.enrichUserWithMedia = async function (user, handle) {
    if (!user || user.is_private) return user;
    NS.normalizeUserId(user);

    var count = NS.MEDIA_FETCH_COUNT || 24;
    var referer = 'https://www.instagram.com/' + handle + '/';
    var parsed = NS.parseTimelineEdges(user, handle);
    var seenCodes = {};
    parsed.forEach(function (p) { seenCodes[p.shortcode] = true; });

    if (user.id) {
      var feedItems = await NS.fetchUserFeed(user.id, count, referer);
      feedItems.forEach(function (item) {
        var p = NS.parseMediaItem(item, handle);
        if (p && p.shortcode && !seenCodes[p.shortcode]) {
          seenCodes[p.shortcode] = true;
          parsed.push(p);
        }
      });
    }

    if (!parsed.length) {
      try {
        var html = await NS.fetchProfileHtmlRaw(handle);
        var htmlItems = NS.parseTimelineFromHtml(html, handle);
        htmlItems.forEach(function (p) {
          if (p.shortcode && !seenCodes[p.shortcode]) {
            seenCodes[p.shortcode] = true;
            parsed.push(p);
          }
        });
      } catch (e) {
        /* ignore html fallback */
      }
    }

    var reels = parsed.filter(function (p) { return p.type === 'reel'; });
    var posts = parsed.filter(function (p) { return p.type !== 'reel'; });

    if (user.id) {
      var reelItems = await NS.fetchUserReels(user.id, count, referer);
      reelItems.forEach(function (item) {
        var p = NS.parseMediaItem(item, handle);
        if (p && p.type === 'reel' && p.shortcode && !seenCodes[p.shortcode]) {
          seenCodes[p.shortcode] = true;
          reels.push(p);
        }
      });
    }

    var allMedia = posts.concat(reels);
    allMedia.sort(function (a, b) { return (b.taken_at || 0) - (a.taken_at || 0); });

    var commentItems = Math.min(NS.COMMENT_ITEMS_LIMIT || 10, allMedia.length);
    for (var i = 0; i < commentItems; i++) {
      if (allMedia[i].comment_count > 0 && allMedia[i].id) {
        await NS.sleep(350);
        allMedia[i].comments = await NS.fetchMediaComments(allMedia[i].id, NS.COMMENT_FETCH_LIMIT || 10);
      }
    }

    posts = allMedia.filter(function (p) { return p.type !== 'reel'; });
    reels = allMedia.filter(function (p) { return p.type === 'reel'; });

    user.recent_posts = posts;
    user.recent_reels = reels;
    user.latest_post = allMedia[0] || null;
    if (user.latest_post && user.latest_post.taken_at) {
      user.latest_post_at = user.latest_post.taken_at;
    }
    return user;
  };

  NS.fetchLatestPostTimestamp = async function (userId, referer) {
    if (!userId) return null;
    try {
      var resp = await fetch(
        'https://www.instagram.com/api/v1/feed/user/' + userId + '/?count=1',
        { headers: NS.apiHeaders(referer), credentials: 'include' },
      );
      if (!resp.ok) return null;
      var data = await resp.json();
      var item = data && data.items && data.items[0];
      return (item && (item.taken_at || item.device_timestamp)) || null;
    } catch (e) {
      return null;
    }
  };

  NS.parseFromHtml = function (html, handle) {
    var result = { username: handle };
    var pics = NS.extractProfilePicsFromHtml(html);
    result.profile_pic_url = pics.profile_pic_url;
    result.profile_pic_url_hd = pics.profile_pic_url_hd;

    var bio = html.match(/"biography"\s*:\s*"((?:\\.|[^"\\])*)"/);
    if (bio) result.biography = NS.unescapeJsonString(bio[1]);

    var name = html.match(/"full_name"\s*:\s*"((?:\\.|[^"\\])*)"/);
    if (name) result.full_name = NS.unescapeJsonString(name[1]);

    var ext = html.match(/"external_url"\s*:\s*"((?:\\.|[^"\\])*)"/);
    if (ext && ext[1]) result.external_url = NS.unescapeJsonString(ext[1]);

    var verified = html.match(/"is_verified"\s*:\s*(true|false)/);
    if (verified) result.is_verified = verified[1] === 'true';

    var followers = html.match(/"edge_followed_by"\s*:\s*\{\s*"count"\s*:\s*(\d+)/);
    if (followers) result.follower_count = parseInt(followers[1], 10);

    var following = html.match(/"edge_follow"\s*:\s*\{\s*"count"\s*:\s*(\d+)/);
    if (following) result.following_count = parseInt(following[1], 10);

    var posts = html.match(/"edge_owner_to_timeline_media"\s*:\s*\{\s*"count"\s*:\s*(\d+)/);
    if (posts) result.post_count = parseInt(posts[1], 10);

    var category = html.match(/"category_name"\s*:\s*"((?:\\.|[^"\\])*)"/);
    if (category) result.category_name = NS.unescapeJsonString(category[1]);

    var bizCat = html.match(/"business_category_name"\s*:\s*"((?:\\.|[^"\\])*)"/);
    if (bizCat) result.business_category_name = NS.unescapeJsonString(bizCat[1]);

    var userId = html.match(/"profilePage_(\d+)"/) || html.match(/"owner"\s*:\s*\{\s*"id"\s*:\s*"(\d+)"/);
    if (userId) result.id = userId[1];

    var tsMatch = html.match(/"taken_at_timestamp"\s*:\s*(\d{10})/);
    if (tsMatch) result.latest_post_at = parseInt(tsMatch[1], 10);

    result.business_address = NS.extractAddressFromHtml(html);
    result.bio_links_parsed = NS.extractBioLinksFromHtml(html);

    var fbPage = html.match(/"connected_fb_page"\s*:\s*"((?:\\.|[^"\\])*)"/);
    if (fbPage) result.connected_fb_page = NS.unescapeJsonString(fbPage[1]);

    return result;
  };

  NS.fetchProfileApi = async function (handle) {
    var referer = 'https://www.instagram.com/' + handle + '/';
    var resp = await fetch(
      'https://www.instagram.com/api/v1/users/web_profile_info/?username=' + encodeURIComponent(handle),
      { headers: NS.apiHeaders(referer), credentials: 'include' },
    );
    if (!resp.ok) return null;
    var data = await resp.json();
    var user = data && data.data && data.data.user;
    if (!user) return null;
    NS.enrichUserFromApi(user);

    if (!user.latest_post_at && user.id) {
      user.latest_post_at = await NS.fetchLatestPostTimestamp(user.id, referer);
    }

    return user;
  };

  NS.fetchProfileHtmlRaw = async function (handle) {
    var resp = await fetch('https://www.instagram.com/' + encodeURIComponent(handle) + '/', {
      credentials: 'include',
      headers: { Accept: 'text/html,application/xhtml+xml' },
    });
    if (!resp.ok) return '';
    return resp.text();
  };

  NS.fetchProfileHtml = async function (handle) {
    var html = await NS.fetchProfileHtmlRaw(handle);
    if (!html) return null;
    return NS.parseFromHtml(html, handle);
  };

  NS.fetchProfileHtmlMerged = async function (user, handle) {
    var html = await NS.fetchProfileHtmlRaw(handle);
    if (!html) return user;
    return NS.mergeHtmlIntoUser(user || { username: handle }, html, handle);
  };

  NS.fetchProfile = async function (handle) {
    var clean = String(handle || '').replace(/^@/, '').toLowerCase();
    if (!clean) return null;

    var user = null;
    try {
      user = await NS.fetchProfileApi(clean);
    } catch (e) {
      user = null;
    }

    try {
      user = await NS.fetchProfileHtmlMerged(user, clean);
    } catch (e) {
      if (!user) {
        try {
          user = await NS.fetchProfileHtml(clean);
        } catch (e2) {
          user = null;
        }
      }
    }

    if (user && !user.latest_post_at && user.id) {
      try {
        user.latest_post_at = await NS.fetchLatestPostTimestamp(user.id);
      } catch (e) {
        /* ignore */
      }
    }

    if (user && !user.is_private) {
      try {
        user = await NS.enrichUserWithMedia(user, clean);
      } catch (e) {
        /* ignore media enrichment failure */
      }
    }

    if (user) {
      user.username = user.username || clean;
      user.profile_pic_url_hd = NS.normalizePicUrl(
        user.profile_pic_url_hd || user.profile_pic_url,
      );
      user.profile_pic_url = NS.normalizePicUrl(
        user.profile_pic_url || user.profile_pic_url_hd,
      );

      var picForDownload = user.profile_pic_url_hd || user.profile_pic_url;
      if (picForDownload) {
        try {
          var dataUrl = await NS.fetchProfilePicDataUrl(picForDownload);
          if (dataUrl) user.profile_picture_data = dataUrl;
        } catch (e) {
          /* ignore download failure */
        }
      }
    }

    return user;
  };
}());
