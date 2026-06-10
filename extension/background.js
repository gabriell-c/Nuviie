chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'DOWNLOAD') {
    chrome.downloads.download(msg.payload, () => sendResponse({ ok: true }));
    return true;
  }
  return false;
});
