from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import Prompt, PromptCategory


class PromptLibraryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='promptlib@test.com',
            email='promptlib@test.com',
            password='testpassword123',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.category = PromptCategory.objects.create(name='Vendas', color='#6366f1')

    def test_category_crud(self):
        list_url = reverse('prompt-category-list')
        resp = self.client.get(list_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

        create_resp = self.client.post(list_url, {'name': 'Instagram', 'color': '#ec4899'}, format='json')
        self.assertEqual(create_resp.status_code, 201)
        cat_id = create_resp.data['id']

        patch_resp = self.client.patch(
            reverse('prompt-category-detail', args=[cat_id]),
            {'name': 'Instagram Ads'},
            format='json',
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.data['name'], 'Instagram Ads')

    def test_prompt_crud_and_filters(self):
        Prompt.objects.create(
            category=self.category,
            title='Abordagem fria',
            content='Olá {{nome}}, vi seu perfil...',
        )
        other = PromptCategory.objects.create(name='Contratos', color='#10b981')
        Prompt.objects.create(category=other, title='Follow-up', content='Retomando contato...')

        list_url = reverse('prompt-list')
        self.assertEqual(self.client.get(list_url).data.__len__(), 2)

        filtered = self.client.get(list_url, {'category': self.category.id})
        self.assertEqual(len(filtered.data), 1)
        self.assertEqual(filtered.data[0]['title'], 'Abordagem fria')

        search = self.client.get(list_url, {'search': 'follow'})
        self.assertEqual(len(search.data), 1)

        create = self.client.post(
            list_url,
            {'title': 'Novo', 'content': 'Texto do prompt', 'category': self.category.id},
            format='json',
        )
        self.assertEqual(create.status_code, 201)
        prompt_id = create.data['id']

        delete = self.client.delete(reverse('prompt-detail', args=[prompt_id]))
        self.assertEqual(delete.status_code, 204)

    def test_cannot_delete_category_with_prompts(self):
        Prompt.objects.create(category=self.category, title='X', content='Y')
        resp = self.client.delete(reverse('prompt-category-detail', args=[self.category.id]))
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(PromptCategory.objects.filter(pk=self.category.pk).exists())

    def test_page_requires_login(self):
        anon = APIClient()
        resp = anon.get(reverse('prompt_library'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login', resp.url)

    def test_page_authenticated(self):
        client = APIClient()
        client.force_login(self.user)
        resp = client.get(reverse('prompt_library'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Biblioteca de Prompts')
