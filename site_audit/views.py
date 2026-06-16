import logging
import threading
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import close_old_connections
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from leads.models import Lead

from .export import audit_to_json, audit_to_markdown
from .models import SiteAuditReport, SiteAuditVisualAsset
from .pagespeed import run_full_audit
from .serializers import SiteAuditCreateSerializer, SiteAuditReportSerializer

logger = logging.getLogger(__name__)


def _apply_period_filter(qs, period: str):
    if not period or period == 'all':
        return qs
    today = timezone.localdate()
    if period == 'today':
        start = today
    elif period == 'yesterday':
        start = today - timedelta(days=1)
        return qs.filter(created_at__date=start)
    elif period in ('7d', '30d', '90d', '365d'):
        days = int(period.replace('d', ''))
        start = today - timedelta(days=days - 1)
    else:
        return qs
    return qs.filter(created_at__date__gte=start, created_at__date__lte=today)


def _apply_date_range_filter(qs, date_from: str | None, date_to: str | None):
    if date_from:
        d = parse_date(date_from)
        if d:
            qs = qs.filter(created_at__gte=timezone.make_aware(datetime.combine(d, time.min)))
    if date_to:
        d = parse_date(date_to)
        if d:
            qs = qs.filter(created_at__lte=timezone.make_aware(datetime.combine(d, time.max)))
    return qs


def _run_audit_async(report_id: int) -> None:
    close_old_connections()
    try:
        report = SiteAuditReport.objects.get(pk=report_id)
        report.status = SiteAuditReport.STATUS_RUNNING
        report.save(update_fields=['status'])

        result = run_full_audit(report.url, report_id=report_id)
        report.scores = result['scores']
        report.core_web_vitals = result['core_web_vitals']
        report.recommendations = result['recommendations']
        report.summary = result['summary']
        report.status = SiteAuditReport.STATUS_COMPLETED
        report.completed_at = timezone.now()
        report.error_message = ''
        report.save()
    except Exception as exc:
        logger.exception('[SiteAudit] Falha report %s', report_id)
        SiteAuditReport.objects.filter(pk=report_id).update(
            status=SiteAuditReport.STATUS_FAILED,
            error_message=str(exc)[:2000],
            completed_at=timezone.now(),
        )


class SiteAuditViewSet(viewsets.ModelViewSet):
    serializer_class = SiteAuditReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = SiteAuditReport.objects.filter(user=self.request.user).select_related('lead')
        lead_param = self.request.query_params.get('lead')
        search = self.request.query_params.get('search')
        period = self.request.query_params.get('period')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if lead_param:
            qs = qs.filter(lead_id=lead_param)
        if search:
            qs = qs.filter(url__icontains=search)
        if period and not (date_from or date_to):
            qs = _apply_period_filter(qs, period)
        else:
            qs = _apply_date_range_filter(qs, date_from, date_to)
        return qs

    def create(self, request, *args, **kwargs):
        ser = SiteAuditCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        url = ser.validated_data['url']
        lead_id = ser.validated_data.get('lead_id')

        lead = None
        if lead_id:
            lead = Lead.objects.filter(user=request.user, pk=lead_id).first()
            if not lead:
                return Response({'error': 'Lead não encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

        report = SiteAuditReport.objects.create(
            user=request.user,
            lead=lead,
            url=url,
            status=SiteAuditReport.STATUS_PENDING,
        )
        thread = threading.Thread(target=_run_audit_async, args=(report.pk,), daemon=True)
        thread.start()
        return Response(SiteAuditReportSerializer(report).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='link-lead')
    def link_lead(self, request, pk=None):
        report = self.get_object()
        lead_id = request.data.get('lead_id')
        if lead_id is None or lead_id == '':
            report.lead = None
            report.save(update_fields=['lead'])
            return Response(SiteAuditReportSerializer(report).data)

        lead = Lead.objects.filter(user=request.user, pk=lead_id).first()
        if not lead:
            return Response({'error': 'Lead não encontrado.'}, status=status.HTTP_400_BAD_REQUEST)
        report.lead = lead
        report.save(update_fields=['lead'])
        return Response(SiteAuditReportSerializer(report).data)

    @action(detail=True, methods=['get'], url_path='export')
    def export_audit(self, request, pk=None):
        report = self.get_object()
        if report.status != SiteAuditReport.STATUS_COMPLETED:
            return Response({'error': 'Auditoria ainda não concluída.'}, status=status.HTTP_400_BAD_REQUEST)

        fmt = (request.query_params.get('file_type') or 'md').lower()
        safe_name = report.url.replace('https://', '').replace('http://', '').replace('/', '_')[:40]
        if fmt == 'json':
            content = audit_to_json(report)
            filename = f'audit-{safe_name}.json'
            content_type = 'application/json; charset=utf-8'
        else:
            content = audit_to_markdown(report)
            filename = f'audit-{safe_name}.md'
            content_type = 'text/markdown; charset=utf-8'

        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @action(detail=True, methods=['get'], url_path=r'visual/(?P<asset_id>[^/.]+)')
    def visual_asset(self, request, pk=None, asset_id=None):
        report = self.get_object()
        asset = SiteAuditVisualAsset.objects.filter(
            report=report, asset_id=asset_id,
        ).first()
        if not asset:
            raise Http404
        if asset.expires_at < timezone.now():
            raise Http404
        from pathlib import Path
        path = Path(settings.MEDIA_ROOT) / asset.file
        if not path.exists():
            alt = path.with_suffix('.webp')
            if alt.exists():
                path = alt
            else:
                raise Http404
        content_type = 'image/avif' if path.suffix == '.avif' else 'image/webp'
        return FileResponse(open(path, 'rb'), content_type=content_type)


def site_audit_dashboard_view(request):
    return render(request, 'site_audit/dashboard.html', {'current_page': 'site_audit'})
