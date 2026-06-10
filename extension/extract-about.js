/* global NuviieMaps */
window.NuviieMaps = window.NuviieMaps || {};

NuviieMaps.extractAboutAmenities = () => {
  const items = [];
  const seen = new Set();
  const selectors = [
    'div.iP2t7d span', 'div.E0DTEd span', 'li.hpLkke span',
    'div.sSHqwe span', 'div.lX8Tbe span', 'div.ekb8yd span',
    'div.Io6YTe', 'ul.ZjVtHb li',
    '[aria-label*="Aceita"]', '[aria-label*="Wi-Fi"]',
    '[aria-label*="Acessív"]', '[aria-label*="Estacionamento"]',
    '[aria-label*="Pagamento"]', '[aria-label*="Refeição"]',
    '[aria-label*="Serviço"]', '[aria-label*="Crianças"]',
    '[aria-label*="Animal"]', '[aria-label*="LGBTQ"]',
  ];
  const skipRe = /^(Rotas|Salvar|Compartilhar|Avaliar|Ligar|Enviar|Sugerir|Adicionar|Ordenar|Pesquisar|Avaliações|Sobre|Visão geral|Serviços|Produtos|Ver|Abrir|Fechar|Mais|Menos|Editar|Denunciar)$/i;
  for (const sel of selectors) {
    for (const el of document.querySelectorAll(sel)) {
      const t = (el.getAttribute('aria-label') || el.textContent || '').trim().replace(/\s+/g, ' ');
      if (t && t.length > 3 && t.length < 120 && !seen.has(t) && !skipRe.test(t)) {
        seen.add(t);
        items.push(t);
      }
      if (items.length >= 50) break;
    }
    if (items.length >= 50) break;
  }
  return items;
};
