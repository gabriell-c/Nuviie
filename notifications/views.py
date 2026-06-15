from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from django.utils import timezone

from .models import Notification
from .serializers import NotificationSerializer
from .services import check_deadline_notifications


class NotificationPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = 'page_size'


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NotificationPagination

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).select_related('lead')

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        check_deadline_notifications()
        n = self.get_queryset().filter(read_at__isnull=True).count()
        return Response({'count': n})

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        n = self.get_object()
        if not n.read_at:
            n.read_at = timezone.now()
            n.save(update_fields=['read_at'])
        return Response(NotificationSerializer(n).data)

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(read_at__isnull=True).update(
            read_at=timezone.now(),
        )
        return Response({'updated': updated})
