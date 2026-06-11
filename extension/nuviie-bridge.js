/** Ponte extensão → página Nuviie (Kanban) para refresh após import. */
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'NUVIIE_LEADS_UPDATED') {
    window.dispatchEvent(new CustomEvent('nuviie-leads-updated', { detail: msg }));
    sendResponse({ ok: true });
  }
  return false;
});
