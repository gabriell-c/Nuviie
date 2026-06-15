"""Filtros de período para lançamentos financeiros."""

from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    s = str(value).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def resolve_period(params) -> tuple[date | None, date | None]:
    """Retorna (início, fim) inclusivos ou (None, None) = sem filtro de data."""
    period = (params.get('period') or 'all').strip().lower()
    today = timezone.localdate()

    if period in ('', 'all'):
        return None, None
    if period == 'today':
        return today, today
    if period == '3d':
        return today - timedelta(days=2), today
    if period == '7d':
        return today - timedelta(days=6), today
    if period == '30d':
        return today - timedelta(days=29), today
    if period == '90d':
        return today - timedelta(days=89), today
    if period == '365d':
        return today - timedelta(days=364), today
    if period == 'single':
        d = _parse_date(params.get('date_on'))
        return (d, d) if d else (None, None)
    if period == 'range':
        df = _parse_date(params.get('date_from'))
        dt = _parse_date(params.get('date_to'))
        if df and dt:
            if df > dt:
                df, dt = dt, df
            return df, dt
        if df:
            return df, df
    # Fallback: date_from/date_to explícitos
    df = _parse_date(params.get('date_from'))
    dt = _parse_date(params.get('date_to'))
    if df and dt:
        if df > dt:
            df, dt = dt, df
        return df, dt
    if df:
        return df, df
    return None, None


def apply_period_filter(qs, params):
    df, dt = resolve_period(params)
    if df and dt:
        return qs.filter(date__gte=df, date__lte=dt)
    return qs


def chart_bucket_range(params) -> tuple[date, date]:
    """Intervalo para buckets do gráfico (respeita filtro ou últimos 6 meses)."""
    df, dt = resolve_period(params)
    today = timezone.localdate()
    if df and dt:
        return df, dt
    from dateutil.relativedelta import relativedelta
    start = today - relativedelta(months=5)
    return start.replace(day=1), today


def build_chart_buckets(date_from: date, date_to: date) -> tuple[list[str], str]:
    """Gera labels e granularidade: day | month."""
    span = (date_to - date_from).days
    labels: list[str] = []
    if span <= 45:
        d = date_from
        while d <= date_to:
            labels.append(d.isoformat())
            d += timedelta(days=1)
        return labels, 'day'
    from dateutil.relativedelta import relativedelta
    d = date_from.replace(day=1)
    end = date_to.replace(day=1)
    while d <= end:
        labels.append(d.strftime('%Y-%m'))
        d += relativedelta(months=1)
    if not labels:
        labels = [date_from.strftime('%Y-%m')]
    return labels, 'month'
