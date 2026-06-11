"""Geração de PDF fiel ao MODELO CONTRATO NUVIIE.pdf"""

from __future__ import annotations

import os
import re

from django.conf import settings
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from .nuviie_template import NUVIIE_BLUE, render_sections

NUVIIE_BLUE_RL = colors.HexColor(NUVIIE_BLUE)
LOGO_PATH = settings.BASE_DIR / 'static' / 'imgs' / 'logo_branca.png'


def _escape_xml(text: str) -> str:
    return (
        text.replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('\n', '<br/>')
    )


class NuviieContractCanvas(canvas.Canvas):
    """Canvas com cabeçalho Nuviie (logo + barra azul) na primeira página."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_header()
            super().showPage()
        super().save()

    def _draw_header(self):
        page_w, page_h = A4
        logo_size = 20 * mm
        bar_h = 8 * mm

        if self._pageNumber == 1:
            self.setFillColor(NUVIIE_BLUE_RL)
            self.rect(0, page_h - logo_size, logo_size, logo_size, fill=1, stroke=0)
            if LOGO_PATH.exists():
                self.drawImage(
                    str(LOGO_PATH),
                    3 * mm, page_h - logo_size + 3 * mm,
                    width=logo_size - 6 * mm,
                    height=logo_size - 6 * mm,
                    preserveAspectRatio=True,
                    mask='auto',
                )
            bar_x = logo_size
            bar_w = page_w - bar_x
            self.rect(bar_x, page_h - bar_h, bar_w, bar_h, fill=1, stroke=0)


def generate_nuviie_contract_pdf(filled_data: dict, output_path: str, contract_title: str):
    sections = render_sections(filled_data)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=32 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=13, leading=16,
        alignment=TA_CENTER, spaceAfter=14, spaceBefore=6,
        textColor=colors.HexColor('#1a1a1a'),
    )
    party_style = ParagraphStyle(
        'PartyLabel', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=11, leading=14,
        alignment=TA_LEFT, spaceBefore=10, spaceAfter=4,
        textColor=colors.HexColor('#1a1a1a'),
    )
    clause_style = ParagraphStyle(
        'Clause', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=11, leading=14,
        alignment=TA_LEFT, spaceBefore=14, spaceAfter=6,
        textColor=colors.HexColor('#1a1a1a'),
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'],
        fontName='Helvetica', fontSize=11, leading=16,
        alignment=TA_JUSTIFY, spaceAfter=8,
        textColor=colors.HexColor('#1a1a1a'),
    )
    intro_style = ParagraphStyle(
        'Intro', parent=body_style, alignment=TA_LEFT, spaceAfter=10,
    )
    sig_style = ParagraphStyle(
        'Sig', parent=body_style, alignment=TA_LEFT, spaceBefore=4,
    )

    style_map = {
        'title': title_style,
        'intro': intro_style,
        'party_label': party_style,
        'clause': clause_style,
        'body': body_style,
        'signature': sig_style,
    }

    story = []
    for section in sections:
        text = section.get('text', '').strip()
        if not text:
            continue
        style = style_map.get(section.get('style', 'body'), body_style)
        story.append(Paragraph(_escape_xml(text), style))

    story.append(Spacer(1, 20 * mm))
    contratante = filled_data.get('assinatura_contratante', '')
    sig_data = [
        [Paragraph('_______________________________________', body_style),
         Paragraph('_______________________________________', body_style)],
        [Paragraph(contratante or 'CONTRATANTE', party_style),
         Paragraph('Gabriel Cardoso - Nuviie', party_style)],
    ]
    sig_table = Table(sig_data, colWidths=[85 * mm, 85 * mm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(sig_table)

    doc.build(story, canvasmaker=NuviieContractCanvas)
