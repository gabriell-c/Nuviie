/**
 * Nuviie Calendar — single date + date range picker helpers for Alpine.
 */
window.NuviieCalendar = window.NuviieCalendar || {};

(function (NC) {
  'use strict';

  const MONTHS = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];

  NC.pad = (n) => String(n).padStart(2, '0');

  NC.toIso = (y, m, d) => `${y}-${NC.pad(m + 1)}-${NC.pad(d)}`;

  NC.parseIso = (iso) => {
    if (!iso) return null;
    const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return null;
    return { y: +m[1], m: +m[2] - 1, d: +m[3] };
  };

  NC.formatBr = (iso) => {
    const p = NC.parseIso(iso);
    if (!p) return '';
    return `${NC.pad(p.d)}/${NC.pad(p.m + 1)}/${p.y}`;
  };

  NC.createState = (mode = 'single') => ({
    mode,
    open: false,
    viewYear: new Date().getFullYear(),
    viewMonth: new Date().getMonth(),
    selected: '',
    rangeStart: '',
    rangeEnd: '',
    hover: '',
  });

  NC.monthLabel = (year, month) => `${MONTHS[month]} ${year}`;

  NC.daysInMonth = (year, month) => new Date(year, month + 1, 0).getDate();

  NC.firstWeekday = (year, month) => new Date(year, month, 1).getDay();

  NC.cells = (state) => {
    const y = state.viewYear;
    const m = state.viewMonth;
    const first = NC.firstWeekday(y, m);
    const total = NC.daysInMonth(y, m);
    const cells = [];
    for (let i = 0; i < first; i++) cells.push({ empty: true });
    for (let d = 1; d <= total; d++) {
      const iso = NC.toIso(y, m, d);
      cells.push({
        empty: false,
        day: d,
        iso,
        isToday: iso === NC.toIso(new Date().getFullYear(), new Date().getMonth(), new Date().getDate()),
        isSelected: state.mode === 'single' ? state.selected === iso : false,
        inRange: NC.inRange(iso, state.rangeStart, state.rangeEnd, state.hover),
        isRangeStart: iso === state.rangeStart,
        isRangeEnd: iso === state.rangeEnd || iso === state.hover,
      });
    }
    return cells;
  };

  NC.inRange = (iso, start, end, hover) => {
    if (!start) return false;
    const endIso = end || hover;
    if (!endIso) return iso === start;
    const a = start <= endIso ? start : endIso;
    const b = start <= endIso ? endIso : start;
    return iso >= a && iso <= b;
  };

  NC.pick = (state, iso) => {
    if (state.mode === 'single') {
      state.selected = iso;
      state.open = false;
      return { selected: iso };
    }
    if (!state.rangeStart || (state.rangeStart && state.rangeEnd)) {
      state.rangeStart = iso;
      state.rangeEnd = '';
      return { rangeStart: iso, rangeEnd: '' };
    }
    if (iso < state.rangeStart) {
      state.rangeEnd = state.rangeStart;
      state.rangeStart = iso;
    } else {
      state.rangeEnd = iso;
    }
    state.open = false;
    return { rangeStart: state.rangeStart, rangeEnd: state.rangeEnd };
  };

  NC.prevMonth = (state) => {
    if (state.viewMonth === 0) {
      state.viewMonth = 11;
      state.viewYear -= 1;
    } else state.viewMonth -= 1;
  };

  NC.nextMonth = (state) => {
    if (state.viewMonth === 11) {
      state.viewMonth = 0;
      state.viewYear += 1;
    } else state.viewMonth += 1;
  };

  NC.periodToRange = (period) => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const iso = (d) => NC.toIso(d.getFullYear(), d.getMonth(), d.getDate());
    const end = iso(today);
    if (period === 'today') return { from: end, to: end };
    if (period === 'yesterday') {
      const y = new Date(today);
      y.setDate(y.getDate() - 1);
      const s = iso(y);
      return { from: s, to: s };
    }
    const days = { '7d': 7, '30d': 30, '90d': 90, '365d': 365 }[period];
    if (days) {
      const start = new Date(today);
      start.setDate(start.getDate() - (days - 1));
      return { from: iso(start), to: end };
    }
    return { from: '', to: '' };
  };
})(window.NuviieCalendar);
