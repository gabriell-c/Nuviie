import re
import pdfplumber

def extract_placeholders_from_pdf(pdf_file_path):
    """
    Extracts all variable placeholders from a PDF contract template.
    Matches:
      - Curly braces: {{ nome_completo }} or {{cnpj}}
      - Upper-case brackets: [NOME_CLIENTE] or [CNPJ]
    """
    placeholders = set()
    
    # Regex for {{ variable }}
    curly_regex = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')
    # Regex for [VARIABLE] (uppercase with letters, numbers, and underscores, length >= 3)
    bracket_regex = re.compile(r'\[\s*([A-Z0-9_]{3,})\s*\]')
    
    try:
        with pdfplumber.open(pdf_file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    # Find {{ variables }}
                    for match in curly_regex.findall(text):
                        placeholders.add(match.strip())
                    # Find [VARIABLES]
                    for match in bracket_regex.findall(text):
                        placeholders.add(match.strip())
    except Exception as e:
        print(f"Error parsing PDF: {e}")
        
    return sorted(list(placeholders))
