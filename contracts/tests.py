from django.test import TestCase

from contracts.parser import analyze_contract_pdf


class ContractParserTests(TestCase):
    def test_analyze_blank_lines_and_labels(self):
        """Parser heurístico detecta labels com valor em branco."""
        import tempfile
        import os

        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest('reportlab não instalado')

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            path = tmp.name

        c = canvas.Canvas(path)
        c.drawString(100, 750, 'CONTRATO DE PRESTACAO DE SERVICOS')
        c.drawString(100, 730, 'Contratante: _________________________')
        c.drawString(100, 710, 'Valor: R$ ___________')
        c.drawString(100, 690, '{{ nome_cliente }}')
        c.save()

        try:
            result = analyze_contract_pdf(path)
            keys = result['detected_fields']
            self.assertIn('nome_cliente', keys)
            self.assertTrue(len(result['structure']['blocks']) >= 3)
            self.assertTrue(len(result['field_schema']) >= 1)
        finally:
            os.unlink(path)
