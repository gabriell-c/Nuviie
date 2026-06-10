/* global NuviieMaps */
window.NuviieMaps = window.NuviieMaps || {};

NuviieMaps.extractReviews = () => {
  const reviews = [];
  const seen = new Set();
  const containers = [
    ...document.querySelectorAll('[data-review-id]'),
    ...document.querySelectorAll('div.jftiEf'),
  ];

  for (const c of containers) {
    if (reviews.length >= 10) break;
    const rev = {};

    const authorEl = c.querySelector('div[class*="d4r55"]') ||
      c.querySelector('.d4r55') ||
      c.querySelector('button.al6Kxe div');
    if (authorEl) rev.author = authorEl.textContent.trim();

    const badgeEl = c.querySelector('div[class*="RfnDt"]') || c.querySelector('.RfnDt');
    if (badgeEl) rev.author_badge = badgeEl.textContent.trim();

    const ratingEl = c.querySelector('[aria-label*="estrela"]') ||
      c.querySelector('[aria-label*="star"]');
    if (ratingEl) {
      const m = (ratingEl.getAttribute('aria-label') || '').match(/(\d)/);
      if (m) rev.rating = parseInt(m[1], 10);
    }

    const dateEl = c.querySelector('span[class*="rsqaWe"]') ||
      c.querySelector('span[class*="xRkPPb"]');
    if (dateEl) rev.date = dateEl.textContent.trim();

    const textEl = c.querySelector('span[class*="wiI7pd"]') ||
      c.querySelector('[class*="MyEned"] span') ||
      c.querySelector('div[class*="review-full-text"]');
    if (textEl) rev.text = textEl.textContent.trim().slice(0, 1000);

    const ownerEl = c.querySelector('div[class*="CDe7pd"]') || c.querySelector('.CDe7pd');
    if (ownerEl) {
      const ownerText = ownerEl.querySelector('span[class*="wiI7pd"]');
      const ownerDate = ownerEl.querySelector('span[class*="DZSIDd"]');
      if (ownerText) rev.owner_reply = ownerText.textContent.trim().slice(0, 500);
      if (ownerDate) rev.owner_reply_date = ownerDate.textContent.trim();
    }

    if (!rev.author && !rev.text && !rev.rating) continue;

    const key = [(rev.author || '').toLowerCase(), rev.date || '', (rev.text || '').slice(0, 60)].join('|');
    if (seen.has(key)) continue;
    seen.add(key);
    reviews.push(rev);
  }
  return reviews;
};
