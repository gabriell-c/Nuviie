from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from rest_framework import permissions, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination

from .models import Prompt, PromptCategory
from .serializers import PromptCategorySerializer, PromptSerializer


class PromptPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = 'page_size'
    max_page_size = 100


@login_required
def prompt_library_view(request):
    return render(request, 'prompt_library/library.html', {'current_page': 'prompt_library'})


class PromptCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = PromptCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = PromptCategory.objects.all()

    def perform_destroy(self, instance):
        if instance.prompts.exists():
            raise ValidationError(
                {
                    'detail': (
                        'Não é possível excluir esta categoria porque ainda existem '
                        'prompts vinculados. Mova ou exclua os prompts primeiro.'
                    ),
                },
            )
        instance.delete()


class PromptViewSet(viewsets.ModelViewSet):
    serializer_class = PromptSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PromptPagination

    def get_queryset(self):
        queryset = Prompt.objects.select_related('category').all()
        category_id = self.request.query_params.get('category')
        search = (self.request.query_params.get('search') or '').strip()
        ordering = self.request.query_params.get('ordering') or '-updated_at'

        if category_id:
            queryset = queryset.filter(category_id=category_id)
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(content__icontains=search)
                | Q(category__name__icontains=search),
            )
        allowed = {'-updated_at', 'updated_at', 'title', '-title'}
        if ordering in allowed:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by('-updated_at')
        return queryset
