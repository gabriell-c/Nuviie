from rest_framework import serializers, viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import models
from django.shortcuts import get_object_or_404

from leads.models import Lead
from .models import GeneratedContract
from .lead_link import link_contract_to_lead, unlink_contract_from_lead
from contracts.payment_plan import build_payment_plan


class GeneratedContractSerializer(serializers.ModelSerializer):
    lead_name = serializers.CharField(source='lead.name', read_only=True, allow_null=True)
    download_url = serializers.SerializerMethodField()
    payment_mode = serializers.SerializerMethodField()

    class Meta:
        model = GeneratedContract
        fields = [
            'id', 'name', 'client_name', 'filled_data', 'payment_plan',
            'lead', 'lead_name', 'payment_mode', 'created_at', 'download_url',
        ]
        read_only_fields = ['id', 'created_at', 'payment_plan']

    def get_download_url(self, obj):
        request = self.context.get('request')
        if request:
            from django.urls import reverse
            return request.build_absolute_uri(reverse('download_contract', args=[obj.id]))
        return None

    def get_payment_mode(self, obj):
        return (obj.payment_plan or {}).get('mode')


class GeneratedContractViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GeneratedContract.objects.select_related('lead', 'user').all()
    serializer_class = GeneratedContractSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        search = (self.request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                models.Q(client_name__icontains=search) | models.Q(name__icontains=search),
            )
        lead_id = self.request.query_params.get('lead')
        if lead_id:
            qs = qs.filter(lead_id=lead_id)
        unlinked = self.request.query_params.get('unlinked')
        if unlinked == '1':
            qs = qs.filter(lead__isnull=True)
        return qs

    @action(detail=True, methods=['post'], url_path='link-lead')
    def link_lead(self, request, pk=None):
        contract = self.get_object()
        lead_id = request.data.get('lead_id')
        if not lead_id:
            return Response({'error': 'lead_id obrigatório'}, status=status.HTTP_400_BAD_REQUEST)
        lead = get_object_or_404(Lead, pk=lead_id)
        lead, created_entries = link_contract_to_lead(contract, lead, user=request.user)
        return Response({
            'success': True,
            'lead_id': lead.id,
            'finance_entries_created': len(created_entries),
            'contract': GeneratedContractSerializer(contract, context={'request': request}).data,
        })

    @action(detail=True, methods=['post'], url_path='unlink-lead')
    def unlink_lead(self, request, pk=None):
        contract = self.get_object()
        if contract.lead_id:
            unlink_contract_from_lead(contract, contract.lead)
        return Response({'success': True})
