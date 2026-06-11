from django.test import TestCase

from contracts.nuviie_template import (
    default_values,
    render_paragraphs,
    render_sections,
    build_filled_data_from_post,
    flat_field_schema,
)


class NuviieTemplateTests(TestCase):
    def test_default_values_has_all_fields(self):
        defaults = default_values()
        keys = {f['key'] for f in flat_field_schema()}
        self.assertTrue(keys.issubset(set(defaults.keys()) | {'contract_name'}))

    def test_render_replaces_placeholders(self):
        data = default_values()
        data['nome_cliente'] = 'Empresa Teste LTDA'
        data['cpf_cnpj'] = '12.345.678/0001-99'
        paragraphs = render_paragraphs(data)
        full_text = ' '.join(paragraphs)
        self.assertIn('Empresa Teste LTDA', full_text)
        self.assertNotIn('{{nome_cliente}}', full_text)

    def test_render_sections_marks_headings(self):
        data = default_values()
        sections = render_sections(data)
        titles = [s for s in sections if s.get('style') == 'title']
        self.assertEqual(len(titles), 1)
        self.assertEqual(titles[0]['text'], 'CONTRATO DE PRESTAÇÃO DE SERVIÇOS')

    def test_build_filled_data_from_post(self):
        from django.http import QueryDict
        post = QueryDict(mutable=True)
        post['field_nome_cliente'] = 'Cliente ABC'
        post['field_valor_total'] = '5000'
        data = build_filled_data_from_post(post)
        self.assertEqual(data['nome_cliente'], 'Cliente ABC')
        self.assertEqual(data['valor_total'], '5000')
