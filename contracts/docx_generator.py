"""Geração de contratos em DOCX a partir de structure + valores."""

from __future__ import annotations

import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt


def _replace_in_text(text: str, field_key: str, value: str) -> str:
    val = str(value or '')
    text = re.sub(r'\{\{\s*' + re.escape(field_key) + r'\s*\}\}', val, text)
    text = re.sub(r'\[\s*' + re.escape(field_key) + r'\s*\]', val, text)
    if not val:
        return text
    text = re.sub(r'_{3,}', val, text, count=1)
    text = re.sub(r'\.{5,}', val, text, count=1)
    return text


def _render_block_text(block: dict, filled_data: dict) -> str:
    if block.get('type') != 'variable':
        return block.get('text', '')
    text = block.get('text', '')
    key = block.get('field_key', '')
    value = filled_data.get(key, '')
    return _replace_in_text(text, key, value)


def generate_contract_docx(structure: dict, filled_data: dict, output_path: str, contract_title: str):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Helvetica'
    style.font.size = Pt(10)

    title = doc.add_heading(contract_title.upper(), level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    blocks = (structure or {}).get('blocks', [])
    if not blocks:
        doc.add_paragraph('(Documento vazio — reanalise o modelo PDF.)')
    else:
        for block in blocks:
            rendered = _render_block_text(block, filled_data)
            if not rendered.strip():
                continue
            para = doc.add_paragraph(rendered)
            if re.match(r'^(CLÁUSULA|SEÇÃO|CAPÍTULO|PARÁGRAFO|\d+\.)', rendered, re.IGNORECASE):
                for run in para.runs:
                    run.bold = True

    doc.add_paragraph('')
    doc.add_paragraph('_______________________________________\t\t_______________________________________')
    doc.add_paragraph('CONTRATANTE\t\tCONTRATADA (Nuviie Agência)')

    doc.save(output_path)
