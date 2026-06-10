"""Parser inteligente de contratos PDF — placeholders explícitos e heurísticas."""

from __future__ import annotations

import re
import unicodedata

import pdfplumber

CURLY_RE = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')
BRACKET_RE = re.compile(r'\[\s*([A-Z0-9_]{3,})\s*\]')
BLANK_LINE_RE = re.compile(r'_{3,}|\.{5,}|\[\s*\]')
LABEL_BLANK_RE = re.compile(
    r'^([A-Za-zÀ-ú0-9][A-Za-zÀ-ú0-9\s./\-]{1,40}):\s*(?:_{2,}|\.{3,}|\[\s*\]|\s*)$',
    re.IGNORECASE,
)
LABEL_VALUE_RE = re.compile(
    r'^([A-Za-zÀ-ú0-9][A-Za-zÀ-ú0-9\s./\-]{1,40}):\s*(.+)$',
    re.IGNORECASE,
)
MONEY_RE = re.compile(r'R\$\s*[\d.,]*(?:_{2,}|\.{3,}|\[\s*\])?', re.IGNORECASE)
QUANTITY_RE = re.compile(r'(\d+|X|___+)\s*(páginas?|paginas?|revisões?|revisoes?|dias?|meses?)', re.IGNORECASE)


def _slugify(text: str) -> str:
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^\w\s]', '', text.lower())
    text = re.sub(r'\s+', '_', text.strip())
    return text[:48] or 'campo'


def _field_type(label: str, text: str) -> str:
    combined = f'{label} {text}'.lower()
    if 'r$' in combined or 'valor' in combined or 'preço' in combined or 'preco' in combined:
        return 'money'
    if any(w in combined for w in ('data', 'prazo', 'vencimento', 'início', 'inicio', 'término', 'termino')):
        return 'date'
    if any(w in combined for w in ('quantidade', 'páginas', 'paginas', 'revisões', 'revisoes', 'número', 'numero')):
        return 'number'
    return 'text'


def _unique_key(base: str, used: set[str]) -> str:
    key = _slugify(base)
    if key not in used:
        used.add(key)
        return key
    i = 2
    while f'{key}_{i}' in used:
        i += 1
    final = f'{key}_{i}'
    used.add(final)
    return final


def _extract_full_text(pdf_file_path: str) -> str:
    parts: list[str] = []
    with pdfplumber.open(pdf_file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
    return '\n'.join(parts)


def _detect_variable_line(line: str, used_keys: set[str]) -> dict | None:
    line = line.strip()
    if not line:
        return None

    for match in CURLY_RE.finditer(line):
        key = match.group(1).strip()
        used_keys.add(key)
        return {
            'field_key': key,
            'label': key.replace('_', ' ').title(),
            'field_type': _field_type(key, line),
            'text': line,
        }

    for match in BRACKET_RE.finditer(line):
        key = match.group(1).strip()
        used_keys.add(key)
        return {
            'field_key': key,
            'label': key.replace('_', ' ').title(),
            'field_type': _field_type(key, line),
            'text': line,
        }

    if MONEY_RE.search(line):
        key = _unique_key('valor_monetario', used_keys)
        return {
            'field_key': key,
            'label': 'Valor monetário',
            'field_type': 'money',
            'text': line,
        }

    if QUANTITY_RE.search(line):
        key = _unique_key('quantidade', used_keys)
        return {
            'field_key': key,
            'label': 'Quantidade',
            'field_type': 'number',
            'text': line,
        }

    if BLANK_LINE_RE.search(line):
        key = _unique_key('campo_em_branco', used_keys)
        return {
            'field_key': key,
            'label': 'Campo em branco',
            'field_type': 'text',
            'text': line,
        }

    m = LABEL_BLANK_RE.match(line)
    if m:
        label = m.group(1).strip()
        key = _unique_key(label, used_keys)
        return {
            'field_key': key,
            'label': label,
            'field_type': _field_type(label, line),
            'text': line,
        }

    return None


def analyze_contract_pdf(pdf_file_path: str) -> dict:
    """
    Analisa um PDF e retorna estrutura segmentada + schema de campos.

    Returns:
        detected_fields: list[str] — compatibilidade retroativa
        structure: { blocks: [...] }
        field_schema: [{ key, label, type, default }]
    """
    raw_text = _extract_full_text(pdf_file_path)
    lines = raw_text.split('\n') if raw_text else []
    used_keys: set[str] = set()
    blocks: list[dict] = []
    schema_map: dict[str, dict] = {}

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        var = _detect_variable_line(stripped, used_keys)
        if var:
            blocks.append({
                'type': 'variable',
                'text': var['text'],
                'field_key': var['field_key'],
                'label': var['label'],
                'field_type': var['field_type'],
            })
            if var['field_key'] not in schema_map:
                schema_map[var['field_key']] = {
                    'key': var['field_key'],
                    'label': var['label'],
                    'type': var['field_type'],
                    'default': '',
                }
        else:
            blocks.append({
                'type': 'static',
                'text': stripped,
            })

    field_schema = list(schema_map.values())
    detected_fields = [f['key'] for f in field_schema]

    return {
        'detected_fields': detected_fields,
        'structure': {'blocks': blocks},
        'field_schema': field_schema,
    }


def extract_placeholders_from_pdf(pdf_file_path: str) -> list[str]:
    """Compatibilidade — retorna apenas as chaves detectadas."""
    return analyze_contract_pdf(pdf_file_path)['detected_fields']
