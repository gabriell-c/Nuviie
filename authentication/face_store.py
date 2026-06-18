"""Perfil facial portátil.

O embedding facial fica em `CustomUser.face_encoding` (no banco), que é local
de cada máquina. Para que o cadastro facial sobreviva a trocas de PC e a um
`git clone`, espelhamos o perfil em arquivos JSON versionáveis dentro do repo
(`authentication/face_profiles/<email>.json`) e os restauramos automaticamente
no banco (casando pelo e-mail do usuário).

Observação: o arquivo guarda apenas o vetor (embedding 512-d), não a foto.
"""
import json
import logging
import re
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

PROFILE_DIR = Path(settings.BASE_DIR) / 'authentication' / 'face_profiles'


# ── (de)serialização do embedding ────────────────────────────────────────────
def encode_samples_to_bytes(vectors: list[list[float]]) -> bytes:
    return json.dumps({"samples": vectors}).encode()


def decode_samples_from_bytes(data) -> list[list[float]]:
    if not data:
        return []
    try:
        raw = bytes(data).decode() if not isinstance(data, str) else data
        obj = json.loads(raw)
        if isinstance(obj, dict) and "samples" in obj:
            return obj["samples"]
        if isinstance(obj, list):
            return [obj]
    except Exception:
        pass
    return []


# ── arquivos ──────────────────────────────────────────────────────────────────
def _safe_name(email: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', (email or '').lower()) or 'user'


def _profile_path(email: str) -> Path:
    return PROFILE_DIR / f'{_safe_name(email)}.json'


def export_profile(user) -> bool:
    """Salva o perfil facial do usuário em arquivo versionável. Idempotente."""
    try:
        samples = decode_samples_from_bytes(user.face_encoding)
        if not samples:
            return False
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            'version': 1,
            'email': user.email,
            'username': user.username,
            'face_login_enabled': bool(user.face_login_enabled),
            'samples': samples,
            'exported_at': datetime.now(dt_timezone.utc).isoformat(),
        }
        _profile_path(user.email).write_text(
            json.dumps(payload, indent=2), encoding='utf-8',
        )
        logger.info('Perfil facial exportado para arquivo: %s', user.email)
        return True
    except Exception:
        logger.exception('Falha ao exportar perfil facial')
        return False


def remove_profile(email: str) -> None:
    try:
        path = _profile_path(email)
        if path.exists():
            path.unlink()
            logger.info('Perfil facial removido do arquivo: %s', email)
    except Exception:
        logger.exception('Falha ao remover perfil facial')


def export_all() -> int:
    from .models import CustomUser

    count = 0
    for user in CustomUser.objects.exclude(face_encoding=None):
        if export_profile(user):
            count += 1
    return count


def import_profiles(*, overwrite: bool = False) -> tuple[int, int]:
    """Restaura perfis dos arquivos para os usuários (casando por e-mail).

    Por padrão, só preenche quem ainda não tem encoding no banco. Com
    `overwrite=True`, sobrescreve sempre. Retorna (restaurados, arquivos_lidos).
    """
    from .models import CustomUser

    if not PROFILE_DIR.exists():
        return 0, 0

    restored = 0
    files = list(PROFILE_DIR.glob('*.json'))
    for f in files:
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            logger.warning('Perfil facial inválido (ignorado): %s', f.name)
            continue

        email = data.get('email')
        samples = data.get('samples') or []
        if not email or not samples:
            continue

        user = CustomUser.objects.filter(email__iexact=email).first()
        if not user:
            continue

        existing = decode_samples_from_bytes(user.face_encoding)
        if existing and not overwrite:
            continue

        user.face_encoding = encode_samples_to_bytes(samples)
        if data.get('face_login_enabled'):
            user.face_login_enabled = True
        user.save(update_fields=['face_encoding', 'face_login_enabled'])
        restored += 1
        logger.info('Perfil facial restaurado do arquivo: %s', email)

    return restored, len(files)
