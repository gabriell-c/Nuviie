/**
 * Nuviie Forms — máscaras, parse e validação (BR).
 */
window.NuviieForms = window.NuviieForms || {};

(function (NF) {
  'use strict';

  NF.onlyDigits = (s) => String(s || '').replace(/\D/g, '');

  NF.maskPhone = (value) => {
    const d = NF.onlyDigits(value).slice(0, 11);
    if (d.length <= 2) return d ? `(${d}` : '';
    if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`;
    if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
    return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
  };

  NF.maskCpf = (value) => {
    const d = NF.onlyDigits(value).slice(0, 11);
    if (d.length <= 3) return d;
    if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`;
    if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
    return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
  };

  NF.maskCep = (value) => {
    const d = NF.onlyDigits(value).slice(0, 8);
    if (d.length <= 5) return d;
    return `${d.slice(0, 5)}-${d.slice(5)}`;
  };

  NF.maskDate = (value) => {
    const d = NF.onlyDigits(value).slice(0, 8);
    if (d.length <= 2) return d;
    if (d.length <= 4) return `${d.slice(0, 2)}/${d.slice(2)}`;
    return `${d.slice(0, 2)}/${d.slice(2, 4)}/${d.slice(4)}`;
  };

  NF.maskCurrency = (value) => {
    const digits = NF.onlyDigits(value);
    if (!digits) return '';
    const num = parseInt(digits, 10) / 100;
    return num.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  };

  NF.applyMask = (type, value) => {
    switch (type) {
      case 'phone': return NF.maskPhone(value);
      case 'cpf': return NF.maskCpf(value);
      case 'cep': return NF.maskCep(value);
      case 'date': return NF.maskDate(value);
      case 'currency': return NF.maskCurrency(value);
      default: return value;
    }
  };

  NF.parseCurrency = (str) => {
    if (str == null || str === '') return null;
    const s = String(str).replace(/[^\d,.-]/g, '').replace(/\./g, '').replace(',', '.');
    const n = parseFloat(s);
    return Number.isNaN(n) ? null : n;
  };

  NF.parseDate = (str) => {
    const m = String(str || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (!m) return null;
    const d = parseInt(m[1], 10);
    const mo = parseInt(m[2], 10);
    const y = parseInt(m[3], 10);
    const dt = new Date(y, mo - 1, d);
    if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return null;
    return `${y}-${String(mo).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  };

  NF.formatDateDisplay = (iso) => {
    if (!iso) return '';
    const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return iso;
    return `${m[3]}/${m[2]}/${m[1]}`;
  };

  NF.validateCpf = (cpf) => {
    const d = NF.onlyDigits(cpf);
    if (d.length !== 11 || /^(\d)\1+$/.test(d)) return false;
    let sum = 0;
    for (let i = 0; i < 9; i++) sum += parseInt(d[i], 10) * (10 - i);
    let r = (sum * 10) % 11;
    if (r === 10) r = 0;
    if (r !== parseInt(d[9], 10)) return false;
    sum = 0;
    for (let i = 0; i < 10; i++) sum += parseInt(d[i], 10) * (11 - i);
    r = (sum * 10) % 11;
    if (r === 10) r = 0;
    return r === parseInt(d[10], 10);
  };

  NF.validatePhone = (phone) => {
    const d = NF.onlyDigits(phone);
    return d.length >= 10 && d.length <= 11;
  };

  NF.validateUrl = (url) => {
    if (!url) return true;
    try {
      const u = new URL(url);
      return u.protocol === 'http:' || u.protocol === 'https:';
    } catch {
      return false;
    }
  };

  NF.setFieldError = (el, msg) => {
    if (!el) return;
    el.classList.add('nui-input-error-state');
    let hint = el.parentElement?.querySelector('.nui-field-error');
    if (!hint) {
      hint = document.createElement('p');
      hint.className = 'nui-field-error';
      el.parentElement?.appendChild(hint);
    }
    hint.textContent = msg || '';
    hint.style.display = msg ? 'block' : 'none';
  };

  NF.clearFieldError = (el) => {
    if (!el) return;
    el.classList.remove('nui-input-error-state');
    const hint = el.parentElement?.querySelector('.nui-field-error');
    if (hint) hint.style.display = 'none';
  };

  NF.validateField = (el) => {
    if (!el) return true;
    const type = el.dataset.nuiMask || el.getAttribute('x-nui-mask')?.replace(/'/g, '');
    const required = el.required || el.dataset.required === 'true';
    const val = (el.value || '').trim();
    NF.clearFieldError(el);
    if (required && !val) {
      NF.setFieldError(el, 'Campo obrigatório.');
      return false;
    }
    if (!val) return true;
    if (type === 'cpf' && !NF.validateCpf(val)) {
      NF.setFieldError(el, 'CPF inválido.');
      return false;
    }
    if (type === 'phone' && !NF.validatePhone(val)) {
      NF.setFieldError(el, 'Telefone inválido.');
      return false;
    }
    if (type === 'date' && !NF.parseDate(val)) {
      NF.setFieldError(el, 'Data inválida (dd/mm/aaaa).');
      return false;
    }
    if (type === 'url' && !NF.validateUrl(val)) {
      NF.setFieldError(el, 'URL inválida.');
      return false;
    }
    if (el.type === 'email' && val && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) {
      NF.setFieldError(el, 'E-mail inválido.');
      return false;
    }
    return true;
  };

  NF.validateForm = (root) => {
    if (!root || typeof root.querySelectorAll !== 'function') return true;
    const fields = root.querySelectorAll('[data-nui-mask], [data-nui-validate], [x-nui-mask]');
    let ok = true;
    fields.forEach((el) => {
      if (!NF.validateField(el)) ok = false;
    });
    root.querySelectorAll('[required]').forEach((el) => {
      if (!el.dataset.nuiMask && !el.hasAttribute('x-nui-mask')) {
        if (!NF.validateField(el)) ok = false;
      }
    });
    return ok;
  };

  NF.bindMaskInput = (el) => {
    const type = el.dataset.nuiMask;
    if (!type) return;
    el.addEventListener('input', () => {
      const pos = el.selectionStart;
      const before = el.value;
      el.value = NF.applyMask(type, before);
    });
    el.addEventListener('blur', () => NF.validateField(el));
  };

  NF.init = (root = document) => {
    if (!root || typeof root.querySelectorAll !== 'function') return;
    root.querySelectorAll('[data-nui-mask]').forEach(NF.bindMaskInput);
  };

  document.addEventListener('DOMContentLoaded', () => NF.init());

  document.addEventListener('alpine:init', () => {
    if (!window.Alpine) return;
    Alpine.directive('nui-mask', (el, { expression }, { effect, evaluateLater }) => {
      const getType = evaluateLater(expression);
      effect(() => {
        getType((type) => {
          el.dataset.nuiMask = type;
          NF.bindMaskInput(el);
        });
      });
      el.addEventListener('input', () => {
        const t = el.dataset.nuiMask;
        if (t) el.value = NF.applyMask(t, el.value);
      });
    });
  });
})(window.NuviieForms);
