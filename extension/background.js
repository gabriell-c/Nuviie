importScripts('instagram/runner.js');

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'DOWNLOAD') {
    chrome.downloads.download(msg.payload, () => sendResponse({ ok: true }));
    return true;
  }

  if (msg.type === 'FETCH_IMAGE') {
    const url = msg.url;
    if (!url) {
      sendResponse({ ok: false });
      return false;
    }
    fetch(url, { credentials: 'omit', referrerPolicy: 'no-referrer' })
      .then((r) => {
        if (!r.ok) throw new Error('fetch failed');
        return r.blob();
      })
      .then((blob) => {
        if (blob.size > 500000 || blob.size < 50) {
          sendResponse({ ok: false });
          return;
        }
        const reader = new FileReader();
        reader.onload = () => sendResponse({ ok: true, dataUrl: reader.result });
        reader.onerror = () => sendResponse({ ok: false });
        reader.readAsDataURL(blob);
      })
      .catch(() => sendResponse({ ok: false }));
    return true;
  }

  if (msg.type === 'START_INSTAGRAM_EXTRACTION') {
    NuviieInstagramRunner.run(msg.options || {}).then(sendResponse);
    return true;
  }

  if (msg.type === 'STOP_INSTAGRAM_EXTRACTION') {
    NuviieInstagramRunner.stop();
    sendResponse({ ok: true });
    return false;
  }

  if (msg.type === 'GET_INSTAGRAM_STATE') {
    sendResponse({
      running: NuviieInstagramRunner.state.running,
      leads: NuviieInstagramRunner.state.leads,
      progress: NuviieInstagramRunner.state.progress,
    });
    return false;
  }

  return false;
});
