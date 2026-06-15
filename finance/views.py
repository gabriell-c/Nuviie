import csv
import io
from decimal import Decimal

from django.db.models import Min, Max, Q, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.exceptions import ValidationError

from leads.models import Lead

from .models import FinanceCategory, FinanceEntry
from .serializers import FinanceCategorySerializer, FinanceEntrySerializer
from .services import generate_recurring_occurrence, process_due_recurring_entries
from .period_utils import apply_period_filter, build_chart_buckets, chart_bucket_range
from .export_formats import export_styled_pdf, export_styled_xlsx


class FinancePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class FinanceCategoryViewSet(viewsets.ModelViewSet):
    queryset = FinanceCategory.objects.all()
    serializer_class = FinanceCategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_destroy(self, instance):
        if instance.entries.exclude(status='cancelled').exists():
            raise ValidationError(
                {'detail': 'Não é possível excluir categoria com lançamentos vinculados.'},
            )
        instance.delete()


class FinanceEntryViewSet(viewsets.ModelViewSet):
    queryset = FinanceEntry.objects.select_related(
        'category', 'lead', 'contract', 'created_by',
    ).all()
    serializer_class = FinanceEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = FinancePagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get('entry_type'):
            qs = qs.filter(entry_type=p['entry_type'])
        if p.get('category'):
            qs = qs.filter(category_id=p['category'])
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        if p.get('lead'):
            qs = qs.filter(lead_id=p['lead'])
        qs = apply_period_filter(qs, p)
        search = (p.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(title__icontains=search) | Q(notes__icontains=search)
                | Q(lead__name__icontains=search),
            )
        ordering = p.get('ordering') or '-date'
        allowed = {'date', '-date', 'amount', '-amount', 'title', '-title'}
        if ordering in allowed:
            qs = qs.order_by(ordering, '-id')
        return qs

    def perform_create(self, serializer):
        entry = serializer.save(created_by=self.request.user)
        if entry.is_recurring and entry.recurrence_rule:
            generate_recurring_occurrence(entry)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        qs = self.filter_queryset(self.get_queryset())
        income = qs.filter(entry_type='income', status='confirmed').aggregate(
            t=Sum('amount'),
        )['t'] or Decimal('0')
        expense = qs.filter(entry_type='expense', status='confirmed').aggregate(
            t=Sum('amount'),
        )['t'] or Decimal('0')
        pending_in = qs.filter(
            entry_type='income', status='pending',
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        return Response({
            'income_confirmed': str(income),
            'expense_confirmed': str(expense),
            'balance': str(income - expense),
            'pending_income': str(pending_in),
        })

    @action(detail=False, methods=['get'], url_path='chart-data')
    def chart_data(self, request):
        qs = self.filter_queryset(self.get_queryset()).exclude(status='cancelled')
        period = (request.query_params.get('period') or 'all').strip().lower()
        today = timezone.localdate()

        if period in ('', 'all'):
            from dateutil.relativedelta import relativedelta
            default_start = (today - relativedelta(months=5)).replace(day=1)
            agg = qs.aggregate(mn=Min('date'), mx=Max('date'))
            mn, mx = agg['mn'], agg['mx']
            if mn and mx:
                date_from = min(mn.replace(day=1), default_start)
                date_to = max(mx, today)
            else:
                date_from, date_to = default_start, today
        else:
            date_from, date_to = chart_bucket_range(request.query_params)

        labels, granularity = build_chart_buckets(date_from, date_to)
        buckets = {k: {'income': Decimal('0'), 'expense': Decimal('0')} for k in labels}

        def bucket_key(entry_date):
            if granularity == 'day':
                return entry_date.isoformat()
            return entry_date.strftime('%Y-%m')

        for e in qs.filter(date__gte=date_from, date__lte=date_to):
            key = bucket_key(e.date)
            if key not in buckets:
                buckets[key] = {'income': Decimal('0'), 'expense': Decimal('0')}
                if key not in labels:
                    labels.append(key)
            if e.entry_type == 'income':
                buckets[key]['income'] += e.amount
            else:
                buckets[key]['expense'] += e.amount

        labels = sorted(set(labels), key=lambda x: x)
        by_cat = {}
        cat_colors = {}
        for e in qs.filter(entry_type='expense', date__gte=date_from, date__lte=date_to):
            name = e.category.name
            by_cat[name] = by_cat.get(name, Decimal('0')) + e.amount
            cat_colors[name] = e.category.color
        income_by_cat = {}
        for e in qs.filter(entry_type='income', date__gte=date_from, date__lte=date_to):
            name = e.category.name
            income_by_cat[name] = income_by_cat.get(name, Decimal('0')) + e.amount
            cat_colors[name] = e.category.color

        empty = not any(
            buckets.get(k, {}).get('income', 0) or buckets.get(k, {}).get('expense', 0)
            for k in labels
        )
        return Response({
            'monthly_labels': labels,
            'granularity': granularity,
            'monthly_income': [str(buckets.get(k, {}).get('income', 0)) for k in labels],
            'monthly_expense': [str(buckets.get(k, {}).get('expense', 0)) for k in labels],
            'expense_by_category': {k: str(v) for k, v in by_cat.items()},
            'income_by_category': {k: str(v) for k, v in income_by_cat.items()},
            'category_colors': cat_colors,
            'has_data': not empty,
        })

    @action(detail=False, methods=['get'], url_path='search-leads')
    def search_leads(self, request):
        q = (request.query_params.get('q') or '').strip()
        if len(q) < 2:
            return Response([])
        leads = Lead.objects.filter(user=request.user).filter(
            Q(name__icontains=q) | Q(category__icontains=q) | Q(city__icontains=q)
            | Q(phone_number__icontains=q),
        ).order_by('-updated_at')[:15]
        return Response([
            {
                'id': l.id,
                'name': l.name,
                'status': l.status,
                'city': l.city or '',
                'category': l.category or '',
            }
            for l in leads
        ])

    @action(detail=False, methods=['get'], url_path='export')
    def export_entries(self, request):
        fmt = (request.query_params.get('export_format') or request.query_params.get('format') or 'csv').lower()
        qs = self.filter_queryset(self.get_queryset()).select_related('category', 'lead')
        rows = list(qs[:5000])
        if fmt == 'xlsx':
            try:
                data = export_styled_xlsx(rows, request.query_params)
            except ImportError:
                return Response({'error': 'openpyxl não instalado'}, status=500)
            resp = HttpResponse(
                data,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            resp['Content-Disposition'] = 'attachment; filename="nuviie-financeiro.xlsx"'
            return resp
        if fmt == 'pdf':
            data = export_styled_pdf(rows, request.query_params)
            resp = HttpResponse(data, content_type='application/pdf')
            resp['Content-Disposition'] = 'attachment; filename="nuviie-financeiro.pdf"'
            return resp
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = 'attachment; filename="financeiro.csv"'
        resp.write('\ufeff')
        w = csv.writer(resp)
        w.writerow(['Data', 'Título', 'Tipo', 'Categoria', 'Valor', 'Status', 'Lead', 'Vencimento'])
        for e in rows:
            w.writerow([
                e.date.isoformat(), e.title, e.entry_type,
                e.category.name, e.amount, e.status,
                e.lead.name if e.lead else '',
                e.due_date.isoformat() if e.due_date else '',
            ])
        return resp


@login_required
def finance_dashboard_view(request):
    process_due_recurring_entries()
    return render(request, 'finance/dashboard.html', {'current_page': 'finance'})
