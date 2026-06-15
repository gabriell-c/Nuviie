import csv
import io
from datetime import datetime
from decimal import Decimal

from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import FinanceCategory, FinanceEntry
from .serializers import FinanceCategorySerializer, FinanceEntrySerializer
from .services import generate_recurring_occurrence, process_due_recurring_entries


class FinancePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class FinanceCategoryViewSet(viewsets.ModelViewSet):
    queryset = FinanceCategory.objects.all()
    serializer_class = FinanceCategorySerializer
    permission_classes = [permissions.IsAuthenticated]


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
        if p.get('date_from'):
            qs = qs.filter(date__gte=p['date_from'])
        if p.get('date_to'):
            qs = qs.filter(date__lte=p['date_to'])
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
        qs = self.filter_queryset(self.get_queryset())
        monthly = {}
        for e in qs.filter(status='confirmed'):
            key = e.date.strftime('%Y-%m')
            if key not in monthly:
                monthly[key] = {'income': Decimal('0'), 'expense': Decimal('0')}
            if e.entry_type == 'income':
                monthly[key]['income'] += e.amount
            else:
                monthly[key]['expense'] += e.amount
        labels = sorted(monthly.keys())[-12:]
        by_cat = {}
        for e in qs.filter(entry_type='expense', status='confirmed'):
            name = e.category.name
            by_cat[name] = by_cat.get(name, Decimal('0')) + e.amount
        return Response({
            'monthly_labels': labels,
            'monthly_income': [str(monthly[k]['income']) for k in labels],
            'monthly_expense': [str(monthly[k]['expense']) for k in labels],
            'expense_by_category': {k: str(v) for k, v in by_cat.items()},
        })

    @action(detail=False, methods=['get'], url_path='export')
    def export_entries(self, request):
        fmt = (request.query_params.get('export_format') or request.query_params.get('format') or 'csv').lower()
        qs = self.filter_queryset(self.get_queryset())
        rows = qs[:5000]
        if fmt == 'xlsx':
            try:
                from openpyxl import Workbook
            except ImportError:
                return Response({'error': 'openpyxl não instalado'}, status=500)
            wb = Workbook()
            ws = wb.active
            ws.title = 'Financeiro'
            headers = [
                'Data', 'Título', 'Tipo', 'Categoria', 'Valor', 'Status',
                'Cliente/Lead', 'Vencimento', 'Origem',
            ]
            ws.append(headers)
            for e in rows:
                ws.append([
                    e.date.isoformat(), e.title,
                    e.get_entry_type_display(), e.category.name,
                    float(e.amount), e.get_status_display(),
                    e.lead.name if e.lead else '',
                    e.due_date.isoformat() if e.due_date else '',
                    e.get_source_display(),
                ])
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            resp = HttpResponse(
                buf.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            resp['Content-Disposition'] = 'attachment; filename="financeiro.xlsx"'
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
