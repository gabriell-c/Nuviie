from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .engine import get_field_registry
from .models import ScoringRule
from .recalculate import recalculate_all_leads
from .serializers import ScoringRuleSerializer


@login_required
def scoring_rules_view(request):
    return render(request, 'lead_scoring/rules.html', {'current_page': 'lead_scoring'})


class ScoringRuleViewSet(viewsets.ModelViewSet):
    serializer_class = ScoringRuleSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = ScoringRule.objects.prefetch_related('conditions').all()

    @action(detail=False, methods=['post'], url_path='recalculate')
    def recalculate(self, request):
        count = recalculate_all_leads()
        return Response({'recalculated': count})


class ScoringFieldsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(get_field_registry())
