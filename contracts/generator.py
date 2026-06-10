import os
import re
import pdfplumber
from django.conf import settings
from django.core.files.base import ContentFile
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """
    Custom canvas to calculate total page count and add standard 
    footer details (Page X of Y) and top headers.
    """
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
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        
        # Color definitions
        primary_color = colors.HexColor("#1e293b")  # Slate 800
        muted_color = colors.HexColor("#64748b")    # Slate 500
        border_color = colors.HexColor("#e2e8f0")   # Slate 200

        # Header - Only show if page > 1
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(primary_color)
            self.drawString(54, 750, "NUVIIE DIGITAL AGENCY")
            self.setFont("Helvetica", 8)
            self.drawRightString(558, 750, "Instrumento Particular de Contrato")
            self.setStrokeColor(border_color)
            self.setLineWidth(0.5)
            self.line(54, 742, 558, 742)

        # Footer - Show on all pages
        self.setStrokeColor(border_color)
        self.setLineWidth(0.5)
        self.line(54, 55, 558, 55)
        
        self.setFont("Helvetica", 8)
        self.setFillColor(muted_color)
        self.drawString(54, 42, "Nuviie Hub - Gerador Automático de Contratos")
        self.drawRightString(558, 42, f"Página {self._pageNumber} de {page_count}")
        
        self.restoreState()


def _replace_field_in_text(text: str, key: str, value: str) -> str:
    val_str = str(value or '')
    text = re.sub(r'\{\{\s*' + re.escape(key) + r'\s*\}\}', val_str, text)
    text = re.sub(r'\[\s*' + re.escape(key) + r'\s*\]', val_str, text)
    if val_str:
        text = re.sub(r'_{3,}', val_str, text, count=1)
        text = re.sub(r'\.{5,}', val_str, text, count=1)
    return text


def _blocks_to_paragraphs(structure: dict, filled_data: dict) -> list[str]:
    paragraphs: list[str] = []
    for block in structure.get('blocks', []):
        if block.get('type') == 'variable':
            text = _replace_field_in_text(
                block.get('text', ''),
                block.get('field_key', ''),
                filled_data.get(block.get('field_key', ''), ''),
            )
        else:
            text = block.get('text', '')
        if text.strip():
            paragraphs.append(text.strip())
    return paragraphs


def generate_contract_pdf(template_path, filled_data, output_path, contract_title, structure=None):
    """
    Reads the base template text, replaces placeholders with filled_data, 
    and constructs a premium styled PDF using ReportLab Platypus.
    """
    # 1. Extract base text from template or use structure blocks
    raw_paragraphs: list[str] = []
    if structure and structure.get('blocks'):
        raw_paragraphs = _blocks_to_paragraphs(structure, filled_data)
        processed_text = '\n\n'.join(raw_paragraphs)
    else:
        raw_text = ""
        try:
            with pdfplumber.open(template_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        raw_text += text + "\n\n"
        except Exception as e:
            raw_text = f"Erro ao ler modelo original: {str(e)}"

        # 2. Perform Replacements
        processed_text = raw_text
        for key, value in filled_data.items():
            processed_text = _replace_field_in_text(processed_text, key, value)

        processed_text = processed_text.replace('\r', '')
        raw_paragraphs = [p.strip() for p in processed_text.split('\n\n') if p.strip()]

    # 3. Build the PDF Document
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=54,  # 0.75 in (54 points)
        rightMargin=54,
        topMargin=72,   # 1.0 in
        bottomMargin=72
    )

    styles = getSampleStyleSheet()
    
    # Custom Premium styles
    title_style = ParagraphStyle(
        'ContractTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=30
    )
    
    body_style = ParagraphStyle(
        'ContractBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=15,
        alignment=TA_JUSTIFY,
        textColor=colors.HexColor("#334155"),
        spaceAfter=12
    )
    
    signature_title_style = ParagraphStyle(
        'SignatureTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#0f172a")
    )
    
    signature_body_style = ParagraphStyle(
        'SignatureBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=11,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#475569")
    )

    story = []

    # Document Header - Logo text / Title
    story.append(Paragraph(contract_title.upper(), title_style))
    story.append(Spacer(1, 15))

    # Add paragraphs to the document
    for para_text in raw_paragraphs:
        # Check if the paragraph looks like a title/heading (e.g. "CLÁUSULA PRIMEIRA", "DA EXECUÇÃO")
        if re.match(r'^(CLÁUSULA|SEÇÃO|CAPÍTULO|PARÁGRAFO|\d+\.)', para_text, re.IGNORECASE) or len(para_text) < 60 and para_text.isupper():
            heading_style = ParagraphStyle(
                'ContractHeading',
                parent=body_style,
                fontName='Helvetica-Bold',
                textColor=colors.HexColor("#1e293b"),
                spaceBefore=14,
                spaceAfter=6
            )
            story.append(Paragraph(para_text, heading_style))
        else:
            story.append(Paragraph(para_text, body_style))

    story.append(Spacer(1, 40))

    # 4. Signature Block (2 columns: Contratante / Contratada)
    sig_data = [
        [
            Paragraph("_______________________________________", signature_body_style),
            Paragraph("_______________________________________", signature_body_style)
        ],
        [
            Paragraph("CONTRATANTE", signature_title_style),
            Paragraph("CONTRATADA (Nuviie Agência)", signature_title_style)
        ],
        [
            Paragraph("Representante Legal", signature_body_style),
            Paragraph("Representante Legal", signature_body_style)
        ]
    ]
    
    # 504 is the total printable width (612 - 54*2)
    sig_table = Table(sig_data, colWidths=[252, 252])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    
    story.append(sig_table)

    # Build PDF with custom NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
