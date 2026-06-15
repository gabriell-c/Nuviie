"""Utilitários de detecção de tipo de website — usado por import e serializers."""

import re

_SITE_TYPE_PATTERNS = [
    ('instagram', re.compile(r'instagram\.com/', re.I)),
    ('whatsapp', re.compile(r'(?:wa\.me|api\.whatsapp\.com|chat\.whatsapp\.com)', re.I)),
    ('facebook', re.compile(r'(?:facebook\.com|fb\.com|fb\.me)/', re.I)),
    ('youtube', re.compile(r'youtube\.com/', re.I)),
    ('linktree', re.compile(r'(?:linktr\.ee|linkinbio\.|bio\.site|beacons\.ai|linky\.bio|milkshake\.app|bit\.ly|bitly\.com|tinyurl\.com|goo\.gl|t\.co)', re.I)),
    ('other_social', re.compile(r'(?:tiktok\.com|twitter\.com|x\.com|snapchat\.com|pinterest\.com|threads\.net)', re.I)),
]


def detect_website_type(url: str | None) -> str:
    if not url:
        return 'website'
    for type_name, pattern in _SITE_TYPE_PATTERNS:
        if pattern.search(url):
            return type_name
    return 'website'
