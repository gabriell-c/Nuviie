'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { loadSelfScript } = require('./helpers');

const M = loadSelfScript('instagram/map-lead.js', 'NuviieInstagramMap');

test('detectWebsiteType classifica os tipos de link', () => {
  assert.equal(M.detectWebsiteType('https://minhaempresa.com.br'), 'website');
  assert.equal(M.detectWebsiteType('https://wa.me/5516999998888'), 'whatsapp');
  assert.equal(M.detectWebsiteType('https://instagram.com/fulano'), 'instagram');
  assert.equal(M.detectWebsiteType('https://linktr.ee/fulano'), 'linktree');
  assert.equal(M.detectWebsiteType('https://facebook.com/fulano'), 'facebook');
  // Sem url -> assume website (não penaliza).
  assert.equal(M.detectWebsiteType(''), 'website');
});

test('normalizePhone normaliza para o formato BR (55 + DDD)', () => {
  assert.equal(M.normalizePhone('(16) 99999-8888'), '5516999998888');
  assert.equal(M.normalizePhone('16 9999-8888'), '551699998888');
  assert.equal(M.normalizePhone('+55 (16) 99999-8888'), '5516999998888');
  // Curto demais -> null.
  assert.equal(M.normalizePhone('1234'), null);
  assert.equal(M.normalizePhone(''), null);
  assert.equal(M.normalizePhone(null), null);
});

test('extractEmailFromBio acha e-mail e ignora imagens', () => {
  assert.equal(M.extractEmailFromBio('Fale comigo: Contato@Empresa.com.br hoje'), 'contato@empresa.com.br');
  assert.equal(M.extractEmailFromBio('foto perfil@cdn.png'), null);
  assert.equal(M.extractEmailFromBio('sem email aqui'), null);
  assert.equal(M.extractEmailFromBio(''), null);
});

test('computeEngagementRate calcula taxa média e trata casos vazios', () => {
  const raw = {
    follower_count: 1000,
    recent_posts: [
      { like_count: 100, comment_count: 0 },
      { like_count: 200, comment_count: 0 },
    ],
  };
  // média = 150; 150/1000 = 15%
  assert.equal(M.computeEngagementRate(raw), 15);

  assert.equal(M.computeEngagementRate({ follower_count: 0 }), null);
  assert.equal(M.computeEngagementRate({ follower_count: 1000, recent_posts: [] }), null);
});

test('mapInstagramToLead retorna null sem dados utilizáveis', () => {
  assert.equal(M.mapInstagramToLead(null, {}), null);
  assert.equal(M.mapInstagramToLead({ biography: 'x' }, {}), null);
});

test('mapInstagramToLead marca oportunidade (sem site, com contato, profissional)', () => {
  const lead = M.mapInstagramToLead(
    {
      username: 'cafe.do.ze',
      full_name: 'Café do Zé',
      biography: 'Melhor café! contato@cafedoze.com.br',
      is_business_account: true,
    },
    { city: 'Ribeirão Preto', niche: 'Cafeteria' },
  );
  assert.equal(lead.instagram, '@cafe.do.ze');
  assert.equal(lead.email, 'contato@cafedoze.com.br');
  assert.equal(lead.website, null);
  assert.equal(lead.amenities.is_opportunity, true);
  assert.equal(lead.source, 'instagram');
});

test('mapInstagramToLead detecta site próprio e desmarca oportunidade', () => {
  const lead = M.mapInstagramToLead(
    {
      username: 'loja',
      full_name: 'Loja Top',
      external_url: 'https://lojatop.com.br',
      business_phone_number: '(16) 99999-8888',
      is_business_account: true,
    },
    { city: 'Campinas', niche: 'Varejo' },
  );
  assert.equal(lead.website, 'https://lojatop.com.br');
  assert.equal(lead.website_detected_type, 'website');
  assert.equal(lead.normalized_phone, '5516999998888');
  assert.equal(lead.amenities.is_opportunity, false);
});
