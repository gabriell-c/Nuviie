"""Exportação estruturada de perfil de lead em Markdown e JSON."""

from __future__ import annotations

import json
import re
from typing import Any

from .models import Lead


def _fmt(value: Any, fallback: str = '-') -> str:
    if value is None or value == '':
        return fallback
    return str(value)


def _stars_label(rating: int | float | None) -> str:
    if rating is None:
        return 'Sem nota'
    try:
        n = int(rating)
    except (TypeError, ValueError):
        return _fmt(rating)
    if n <= 0:
        return 'Sem nota'
    return f'{n} estrela{"s" if n != 1 else ""}'


def _normalize_reviews(reviews: list | None) -> list[dict]:
    if not reviews:
        return []
    out = []
    for item in reviews:
        if not isinstance(item, dict):
            continue
        out.append({
            'author': item.get('author') or item.get('nome') or 'Anônimo',
            'rating': item.get('rating') or item.get('nota'),
            'text': item.get('text') or item.get('comentario') or item.get('avaliacao') or '',
            'date': item.get('date') or item.get('data') or '',
        })
    return out


def _normalize_hours(hours: dict | None) -> dict:
    if not isinstance(hours, dict):
        return {}
    labels = {
        'seg': 'Segunda',
        'ter': 'Terça',
        'qua': 'Quarta',
        'qui': 'Quinta',
        'sex': 'Sexta',
        'sab': 'Sábado',
        'dom': 'Domingo',
    }
    result = {}
    for key, label in labels.items():
        if hours.get(key):
            result[label] = hours[key]
    meta = {}
    if hours.get('status_atual'):
        meta['status_atual'] = hours['status_atual']
    if hours.get('aberto_agora') is not None:
        meta['aberto_agora'] = hours['aberto_agora']
    if meta:
        result['_meta'] = meta
    return result


EXPORT_IG_MEDIA_LIMIT = 5
EXPORT_IG_COMMENTS_LIMIT = 3


def _sanitize_instagram_media_item(item: dict) -> dict:
    if not isinstance(item, dict):
        return {}
    out = {k: v for k, v in item.items() if k not in ('image_url', 'video_url', 'carousel')}
    comments = item.get('comments') or []
    if isinstance(comments, list):
        out['comments'] = comments[:EXPORT_IG_COMMENTS_LIMIT]
    return out


def _instagram_export_media_items(amenities: dict) -> list[dict]:
    posts = amenities.get('recent_posts') or []
    reels = amenities.get('recent_reels') or []
    merged = []
    for item in list(posts) + list(reels):
        if isinstance(item, dict):
            merged.append(item)
    merged.sort(key=lambda x: int(x.get('taken_at') or 0), reverse=True)
    return [_sanitize_instagram_media_item(item) for item in merged[:EXPORT_IG_MEDIA_LIMIT]]


def _format_instagram_media_item(item: dict, index: int, *, for_download: bool = True) -> list[str]:
    if for_download:
        item = _sanitize_instagram_media_item(item)
    lines = [f'### Publicação {index} ({item.get("type") or "post"})']
    if item.get('taken_at'):
        try:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(int(item['taken_at']), tz=timezone.utc)
            lines.append(f'- **Data:** {dt.strftime("%d/%m/%Y")}')
        except (TypeError, ValueError, OSError):
            pass
    if item.get('permalink'):
        lines.append(f'- **Link:** {item["permalink"]}')
    if item.get('caption'):
        lines.append(f'- **Legenda:** {item["caption"]}')
    if item.get('like_count') is not None:
        lines.append(f'- **Curtidas:** {item["like_count"]}')
    if item.get('comment_count') is not None:
        lines.append(f'- **Comentários:** {item["comment_count"]}')
    if item.get('view_count') is not None:
        lines.append(f'- **Visualizações:** {item["view_count"]}')
    if not for_download:
        if item.get('image_url'):
            lines.append(f'- **Imagem:** {item["image_url"]}')
        if item.get('video_url'):
            lines.append(f'- **Vídeo:** {item["video_url"]}')
        if item.get('carousel'):
            for si, slide in enumerate(item['carousel'], 1):
                url = slide.get('image_url') or slide.get('video_url') or '-'
                lines.append(f'- **Slide {si}:** {url}')
    comments = item.get('comments') or []
    if comments:
        lines.append('- **Comentários recentes:**')
        for c in comments[:EXPORT_IG_COMMENTS_LIMIT if for_download else len(comments)]:
            author = c.get('author') or 'Anônimo'
            text = (c.get('text') or '').strip() or '(vazio)'
            lines.append(f'  - {author}: {text}')
    lines.append('')
    return lines


def _instagram_export_section(amenities: Any) -> dict:
    if not isinstance(amenities, dict):
        return {}
    latest = amenities.get('latest_post')
    if isinstance(latest, dict):
        latest = _sanitize_instagram_media_item(latest)
    ultimas = _instagram_export_media_items(amenities)
    return {
        'seguidores': amenities.get('follower_count'),
        'seguindo': amenities.get('following_count'),
        'publicacoes_total': amenities.get('post_count'),
        'reels_total': amenities.get('reels_count'),
        'ultima_postagem_em': amenities.get('latest_post_at'),
        'ultima_publicacao': latest,
        'ultimas_publicacoes': ultimas,
    }


def build_lead_profile(lead: Lead) -> dict:
    """Monta dict completo do perfil do lead para exportação."""
    reviews = _normalize_reviews(lead.recent_reviews)
    hours = _normalize_hours(lead.business_hours)

    notes = []
    for note in lead.notes.select_related('user').all()[:50]:
        notes.append({
            'author': note.user.get_full_name() or note.user.username,
            'action_type': note.get_action_type_display(),
            'text': note.note,
            'created_at': note.created_at.strftime('%d/%m/%Y %H:%M'),
        })

    profile = {
        'identificacao': {
            'nome': lead.name,
            'segmento': lead.category,
            'cidade': lead.city,
            'pontuacao_qualidade': lead.quality_score,
            'status': lead.get_status_display(),
            'origem': lead.get_source_display(),
        },
        'contato': {
            'telefone': lead.phone_number,
            'whatsapp': lead.get_whatsapp_link(),
            'website': lead.website,
            'tipo_website_detectado': lead.get_website_detected_type_display() if lead.website_detected_type else None,
            'endereco': lead.address,
        },
        'redes_sociais': {
            'instagram': lead.instagram,
            'facebook': lead.facebook,
            'linkedin': lead.linkedin,
            'youtube': lead.youtube,
            'twitter': lead.twitter,
        },
        'perfil': {
            'bio': lead.bio,
            'foto_perfil_url': lead.profile_picture_url,
            'maps_url': lead.get_maps_link(),
            'maps_share_url': lead.maps_share_url,
        },
        'avaliacoes': {
            'nota_media': lead.rating,
            'total': lead.review_count,
            'recentes': reviews,
        },
        'horario_funcionamento': hours,
        'extras': {
            'faixa_preco': lead.price_range,
            'plus_code': lead.plus_code,
            'total_fotos': lead.total_photos,
            'amenidades': lead.amenities if not isinstance(lead.amenities, dict) else {
                k: v for k, v in lead.amenities.items()
                if k not in ('recent_posts', 'recent_reels', 'latest_post')
            },
        },
        'notas_crm': notes,
    }
    if lead.source == 'instagram' and isinstance(lead.amenities, dict):
        profile['instagram'] = _instagram_export_section(lead.amenities)
    return profile


def lead_to_json(profile: dict, *, indent: int = 2) -> str:
    return json.dumps(profile, ensure_ascii=False, indent=indent)


def lead_to_markdown(profile: dict) -> str:
    ident = profile.get('identificacao', {})
    contato = profile.get('contato', {})
    social = profile.get('redes_sociais', {})
    perfil = profile.get('perfil', {})
    aval = profile.get('avaliacoes', {})
    hours = profile.get('horario_funcionamento', {})
    extras = profile.get('extras', {})
    notes = profile.get('notas_crm', [])

    name = ident.get('nome') or 'Lead'
    lines = [f'# {name}', '']

    lines += ['## Identificação', '']
    lines.append(f'- **Nome:** {_fmt(ident.get("nome"))}')
    lines.append(f'- **Segmento:** {_fmt(ident.get("segmento"))}')
    lines.append(f'- **Cidade:** {_fmt(ident.get("cidade"))}')
    lines.append(f'- **Status CRM:** {_fmt(ident.get("status"))}')
    lines.append(f'- **Pontuação de qualidade:** {_fmt(ident.get("pontuacao_qualidade"))} pts')
    lines.append('')

    lines += ['## Contato', '']
    lines.append(f'- **Telefone:** {_fmt(contato.get("telefone"))}')
    lines.append(f'- **WhatsApp:** {_fmt(contato.get("whatsapp"))}')
    lines.append(f'- **Website:** {_fmt(contato.get("website"))}')
    if contato.get('tipo_website_detectado'):
        lines.append(f'- **Tipo do link de site:** {_fmt(contato.get("tipo_website_detectado"))}')
    lines.append(f'- **Endereço:** {_fmt(contato.get("endereco"))}')
    lines.append('')

    lines += ['## Redes sociais', '']
    for label, key in [
        ('Instagram', 'instagram'),
        ('Facebook', 'facebook'),
        ('LinkedIn', 'linkedin'),
        ('YouTube', 'youtube'),
        ('Twitter / X', 'twitter'),
    ]:
        lines.append(f'- **{label}:** {_fmt(social.get(key))}')
    lines.append('')

    if perfil.get('bio'):
        lines += ['## Descrição / Biografia', '', str(perfil.get('bio')), '']

    ig = profile.get('instagram') or {}
    if ig:
        lines += ['## Instagram — atividade e publicações', '']
        if ig.get('seguidores') is not None:
            lines.append(f'- **Seguidores:** {ig["seguidores"]}')
        if ig.get('seguindo') is not None:
            lines.append(f'- **Seguindo:** {ig["seguindo"]}')
        if ig.get('publicacoes_total') is not None:
            lines.append(f'- **Total de publicações:** {ig["publicacoes_total"]}')
        if ig.get('reels_total') is not None:
            lines.append(f'- **Total de reels:** {ig["reels_total"]}')
        lines.append('')

        latest = ig.get('ultima_publicacao')
        if latest:
            lines += ['### Última publicação', '']
            lines.extend(_format_instagram_media_item(latest, 1))

        ultimas = ig.get('ultimas_publicacoes') or []
        if ultimas:
            lines += [f'## Últimas publicações ({len(ultimas)})', '']
            for i, item in enumerate(ultimas, 1):
                lines.extend(_format_instagram_media_item(item, i))

    rating = aval.get('nota_media')
    total = aval.get('total') or 0
    recentes = aval.get('recentes') or []
    lines += [f'## Avaliações ({_fmt(rating)} — {total})', '']
    if recentes:
        for i, rev in enumerate(recentes, 1):
            comment = (rev.get('text') or '').strip() or '(Sem comentário)'
            lines.append(f'### Avaliação {i}')
            lines.append(f'- **Autor:** {_fmt(rev.get("author"))}')
            lines.append(f'- **Nota:** {_stars_label(rev.get("rating"))}')
            lines.append(f'- **Comentário:** {comment}')
            if rev.get('date'):
                lines.append(f'- **Data:** {rev["date"]}')
            lines.append('')
    else:
        lines.append('_Nenhuma avaliação recente registrada._')
        lines.append('')

    if hours:
        lines += ['## Horário de funcionamento', '']
        hours_copy = dict(hours)
        meta_h = hours_copy.pop('_meta', None)
        if meta_h:
            if meta_h.get('aberto_agora') is True:
                lines.append('- **Status:** Aberto agora')
            elif meta_h.get('aberto_agora') is False:
                lines.append('- **Status:** Fechado agora')
            if meta_h.get('status_atual'):
                lines.append(f'- **Detalhe:** {meta_h["status_atual"]}')
            lines.append('')
        for day, hrs in hours_copy.items():
            lines.append(f'- **{day}:** {_fmt(hrs)}')
        lines.append('')

    amen = extras.get('amenidades') or []
    if extras.get('faixa_preco') or extras.get('plus_code') or extras.get('total_fotos') or amen:
        lines += ['## Informações extras', '']
        if extras.get('faixa_preco'):
            lines.append(f'- **Faixa de preço:** {extras["faixa_preco"]}')
        if extras.get('plus_code'):
            lines.append(f'- **Plus Code:** {extras["plus_code"]}')
        if extras.get('total_fotos'):
            lines.append(f'- **Total de fotos no Maps:** {extras["total_fotos"]}')
        if amen:
            lines.append(f'- **Amenidades:** {", ".join(str(a) for a in amen)}')
        lines.append('')

    if notes:
        lines += ['## Histórico de notas (CRM)', '']
        for note in notes:
            lines.append(f'### {note.get("created_at")} — {note.get("author")} ({note.get("action_type")})')
            lines.append(note.get('text') or '')
            lines.append('')

    return '\n'.join(lines)


def slugify_filename(name: str, max_len: int = 60) -> str:
    slug = re.sub(r'[^\w\s-]', '', name, flags=re.UNICODE)
    slug = re.sub(r'[-\s]+', '-', slug.strip().lower())
    return (slug[:max_len] or 'lead').strip('-')
