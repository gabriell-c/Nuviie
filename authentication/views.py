import random
import re
import logging
import base64
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import cv2

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import CustomUser
from .whatsapp import clean_phone_number, send_whatsapp_otp
from audit.services import log_activity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# InsightFace — backend rápido com ONNX, sem TensorFlow
# ---------------------------------------------------------------------------
_insight_app  = None
_insight_lock = threading.Lock()
FACE_BACKEND  = "insightface"
THRESHOLD     = 0.35   # distância coseno; menor = mais estrito


def _get_insight_app():
    """Carrega o InsightFace uma única vez e mantém em memória."""
    global _insight_app
    if _insight_app is None:
        with _insight_lock:
            if _insight_app is None:
                try:
                    import insightface
                    app = insightface.app.FaceAnalysis(
                        name="buffalo_sc",          # modelo leve ~100 MB
                        providers=["CPUExecutionProvider"],
                    )
                    app.prepare(ctx_id=0, det_size=(320, 320))
                    _insight_app = app
                    logger.info("InsightFace carregado com sucesso (buffalo_sc).")
                except Exception as exc:
                    logger.error("Falha ao carregar InsightFace: %s", exc)
    return _insight_app


# Pré-carrega em background assim que o Django sobe
_preload_thread = threading.Thread(target=_get_insight_app, daemon=True)
_preload_thread.start()


def _decode_image(b64_data: str) -> np.ndarray | None:
    """Decodifica data-URL base64 em array BGR."""
    try:
        _, data = b64_data.split(",", 1)
        arr = np.frombuffer(base64.b64decode(data), np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as exc:
        logger.warning("Falha ao decodificar imagem: %s", exc)
        return None


def compute_face_encoding(img_bgr: np.ndarray) -> list[float] | None:
    """
    Detecta o rosto e retorna o embedding (512-d) usando InsightFace.
    Retorna None se nenhum rosto for encontrado.
    """
    app = _get_insight_app()
    if app is None:
        return None
    try:
        faces = app.get(img_bgr)
        if not faces:
            return None
        # Pega o rosto com maior bounding box (mais próximo da câmera)
        face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))
        return face.embedding.tolist()
    except Exception as exc:
        logger.warning("InsightFace falhou: %s", exc)
        return None


# ── Armazenamento multi-pose ─────────────────────────────────────────────────

def encode_samples_to_bytes(vectors: list[list[float]]) -> bytes:
    return json.dumps({"samples": vectors}).encode()


def decode_samples_from_bytes(data: bytes) -> list[list[float]]:
    try:
        obj = json.loads(data.decode())
        if isinstance(obj, dict) and "samples" in obj:
            return obj["samples"]
        if isinstance(obj, list):
            return [obj]
    except Exception:
        pass
    return []


# ── Comparação ──────────────────────────────────────────────────────────────

def _cosine_distance(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float64)
    vb = np.array(b, dtype=np.float64)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 1.0
    return float(1.0 - np.dot(va, vb) / denom)


def _vec_matches_any_sample(live_vec: list[float],
                             stored_samples: list[list[float]]) -> bool:
    for sample in stored_samples:
        dist = _cosine_distance(live_vec, sample)
        logger.debug("Distância coseno: %.4f (limiar %.4f)", dist, THRESHOLD)
        if dist < THRESHOLD:
            return True
    return False


def is_face_match(stored_encoding: bytes, live_vec: list[float]) -> bool:
    samples = decode_samples_from_bytes(stored_encoding)
    if not samples:
        return False
    return _vec_matches_any_sample(live_vec, samples)


def _majority_vote_match(stored_encoding: bytes, live_vecs: list[list[float]],
                          required_votes: int = 2) -> bool:
    votes = sum(1 for v in live_vecs if is_face_match(stored_encoding, v))
    logger.debug("Votos: %d/%d (necessários %d)", votes, len(live_vecs), required_votes)
    return votes >= required_votes


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

POSE_LABELS = [
    "Olhe direto para a câmera",
    "Vire levemente para a esquerda (~30°)",
    "Vire levemente para a direita (~30°)",
    "Olhe levemente para cima",
]


def face_register_view(request):
    """
    Enroll facial data using 4 guided poses so login works from any angle.
    The frontend sends each pose as pose_0 … pose_3.
    """
    if not request.user.is_authenticated:
        return redirect('login')

    if request.method == 'POST':
        vectors = []
        errors  = []

        def _process_pose(i):
            b64 = request.POST.get(f'pose_{i}')
            if not b64:
                return i, None, f"Pose {i+1} não capturada."
            img = _decode_image(b64)
            if img is None:
                return i, None, f"Imagem da pose {i+1} inválida."
            vec = compute_face_encoding(img)
            if vec is None:
                return i, None, f"Nenhum rosto detectado na pose {i+1}. Tente novamente."
            return i, vec, None

        # Processa todas as poses em paralelo
        results = [None] * len(POSE_LABELS)
        with ThreadPoolExecutor(max_workers=len(POSE_LABELS)) as executor:
            futures = {executor.submit(_process_pose, i): i for i in range(len(POSE_LABELS))}
            for future in as_completed(futures):
                i, vec, err = future.result()
                results[i] = (vec, err)

        for i, (vec, err) in enumerate(results):
            if err:
                errors.append(err)
            elif vec is not None:
                vectors.append(vec)

        if len(vectors) < 2:
            for e in errors:
                messages.error(request, e)
            messages.error(request, "Precisamos de pelo menos 2 poses válidas. Tente novamente.")
            return render(request, 'auth/face_register.html',
                          {'pose_labels': POSE_LABELS, 'face_backend': FACE_BACKEND})

        user = request.user
        user.face_encoding      = encode_samples_to_bytes(vectors)
        user.face_login_enabled = True
        user.save()

        log_activity(
            'face_register',
            f'Cadastro facial concluído ({len(vectors)} poses).',
            user=user,
            entity_type='user',
            entity_id=user.pk,
            request=request,
        )

        messages.success(request, f"Reconhecimento facial cadastrado com {len(vectors)} poses! Login muito mais fácil agora.")
        return redirect('profile')

    return render(request, 'auth/face_register.html',
                  {'pose_labels': POSE_LABELS, 'face_backend': FACE_BACKEND})


def face_login_view(request):
    """Login using facial recognition — AJAX multi-frame with multi-sample matching."""
    if request.method == 'POST':

        # ── AJAX multi-frame submission ──────────────────────────────────
        if request.content_type and 'application/json' in request.content_type:
            try:
                body = json.loads(request.body)
            except Exception:
                return JsonResponse({'status': 'error', 'message': 'JSON inválido.'}, status=400)

            frames_b64 = body.get('frames', [])
            if not frames_b64:
                return JsonResponse({'status': 'error', 'message': 'Nenhum frame enviado.'})

            # Processa frames em paralelo para reduzir latência
            def _process_frame(b64):
                img = _decode_image(b64)
                if img is None:
                    return None
                return compute_face_encoding(img)

            live_vecs = []
            with ThreadPoolExecutor(max_workers=min(len(frames_b64), 4)) as executor:
                for vec in executor.map(_process_frame, frames_b64):
                    if vec is not None:
                        live_vecs.append(vec)

            if not live_vecs:
                return JsonResponse({'status': 'retry',
                                     'message': 'Nenhum rosto detectado. Aproxime-se da câmera e melhore a iluminação.'})

            candidates     = CustomUser.objects.filter(face_login_enabled=True).exclude(face_encoding=None)
            required_votes = max(1, len(live_vecs) // 2)

            for user in candidates:
                if _majority_vote_match(user.face_encoding, live_vecs, required_votes):
                    login(request, user)
                    return JsonResponse({
                        'status':   'success',
                        'message':  f'Bem-vindo, {user.first_name or user.email}!',
                        'redirect': '/dashboard/',
                    })

            return JsonResponse({'status': 'retry',
                                  'message': 'Rosto não reconhecido. Tente novamente.'})

        # ── Regular POST fallback (single frame) ─────────────────────────
        face_data = request.POST.get('face_image')
        if not face_data:
            messages.error(request, "Nenhuma imagem capturada.")
            return render(request, 'auth/face_login.html')

        img = _decode_image(face_data)
        if img is None:
            messages.error(request, "Imagem corrompida. Tente novamente.")
            return render(request, 'auth/face_login.html')

        vec = compute_face_encoding(img)
        if vec is None:
            messages.error(request, "Nenhum rosto detectado. Melhore a iluminação e centralize seu rosto.")
            return render(request, 'auth/face_login.html')

        candidates = CustomUser.objects.filter(face_login_enabled=True).exclude(face_encoding=None)
        for user in candidates:
            if is_face_match(user.face_encoding, vec):
                login(request, user)
                messages.success(request, f"Login facial bem-sucedido! Bem-vindo, {user.first_name or user.email}!")
                return redirect('dashboard')

        messages.error(request, "Rosto não reconhecido. Tente novamente ou use login tradicional.")

    return render(request, 'auth/face_login.html', {'face_backend': FACE_BACKEND})


# ---------------------------------------------------------------------------
# Standard auth views (unchanged logic, kept for completeness)
# ---------------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        email    = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        remember_me = request.POST.get('remember_me')
        if not email or not password:
            messages.error(request, "Por favor, preencha todos os campos.")
            return render(request, 'auth/login.html')
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            request.session.set_expiry(60 * 60 * 24 * 7 if remember_me else 0)
            messages.success(request, f"Bem-vindo de volta, {user.first_name or user.username}!")
            return redirect('dashboard')
        messages.error(request, "Credenciais inválidas. Verifique seu e-mail e senha.")
    return render(request, 'auth/login.html')


def logout_view(request):
    logout(request)
    messages.success(request, "Logout realizado com sucesso.")
    return redirect('login')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        first_name       = request.POST.get('first_name', '').strip()
        last_name        = request.POST.get('last_name', '').strip()
        email            = request.POST.get('email', '').strip()
        phone_number     = request.POST.get('phone_number', '').strip()
        password         = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        if not (first_name and email and password and confirm_password):
            messages.error(request, "Preencha os campos obrigatórios (*).")
            return render(request, 'auth/register.html')
        if password != confirm_password:
            messages.error(request, "As senhas não coincidem.")
            return render(request, 'auth/register.html')
        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "Este e-mail já está cadastrado.")
            return render(request, 'auth/register.html')
        cleaned_phone = clean_phone_number(phone_number)
        if cleaned_phone and CustomUser.objects.filter(phone_number=cleaned_phone).exists():
            messages.error(request, "Este número de WhatsApp já está cadastrado.")
            return render(request, 'auth/register.html')
        try:
            username = email.split('@')[0] + str(random.randint(1000, 9999))
            user = CustomUser.objects.create_user(
                username=username, email=email, password=password,
                first_name=first_name, last_name=last_name,
                phone_number=cleaned_phone,
            )
            login(request, user)
            log_activity(
                'register',
                f'Novo cadastro: {email}.',
                user=user,
                entity_type='user',
                entity_id=user.pk,
                request=request,
            )
            messages.success(request, "Cadastro realizado com sucesso!")
            return redirect('face_register' if request.POST.get('enable_face') else 'dashboard')
        except Exception as e:
            messages.error(request, f"Erro ao registrar: {e}")
    return render(request, 'auth/register.html')


def password_reset_request_view(request):
    if request.method == 'POST':
        phone_number  = request.POST.get('phone_number', '').strip()
        cleaned_phone = clean_phone_number(phone_number)
        if not cleaned_phone:
            messages.error(request, "Por favor, digite um número de WhatsApp válido.")
            return render(request, 'auth/password_reset_request.html')
        try:
            user = CustomUser.objects.get(phone_number=cleaned_phone)
            otp  = f"{random.randint(100000, 999999)}"
            user.whatsapp_otp = otp
            user.whatsapp_otp_created_at = timezone.now()
            user.save()
            success, msg = send_whatsapp_otp(cleaned_phone, otp)
            request.session['reset_phone'] = cleaned_phone
            if success:
                messages.success(request, "Código OTP enviado para seu WhatsApp!")
            else:
                messages.warning(request, "Não foi possível enviar o WhatsApp, mas o código foi gerado.")
            return redirect('password_reset_verify')
        except CustomUser.DoesNotExist:
            messages.error(request, "Este número de WhatsApp não está associado a nenhuma conta.")
    return render(request, 'auth/password_reset_request.html')


def password_reset_verify_view(request):
    reset_phone = request.session.get('reset_phone')
    if not reset_phone:
        messages.error(request, "Sessão expirada. Inicie a recuperação novamente.")
        return redirect('password_reset_request')
    if request.method == 'POST':
        otp_code         = request.POST.get('otp_code', '').strip()
        new_password     = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')
        if not (otp_code and new_password and confirm_password):
            messages.error(request, "Preencha todos os campos.")
            return render(request, 'auth/password_reset_verify.html')
        if new_password != confirm_password:
            messages.error(request, "As senhas não coincidem.")
            return render(request, 'auth/password_reset_verify.html')
        try:
            user = CustomUser.objects.get(phone_number=reset_phone)
            if not user.is_otp_valid():
                messages.error(request, "Código OTP expirado. Solicite um novo.")
                return redirect('password_reset_request')
            if user.whatsapp_otp != otp_code:
                messages.error(request, "Código OTP incorreto.")
                return render(request, 'auth/password_reset_verify.html')
            user.set_password(new_password)
            user.whatsapp_otp = None
            user.whatsapp_otp_created_at = None
            user.save()
            del request.session['reset_phone']
            messages.success(request, "Senha redefinida com sucesso! Faça login com a nova senha.")
            return redirect('login')
        except CustomUser.DoesNotExist:
            messages.error(request, "Usuário não encontrado.")
            return redirect('password_reset_request')
    return render(request, 'auth/password_reset_verify.html', {'reset_phone': reset_phone})


@login_required
def profile_view(request):
    if request.method == 'POST':
        first_name      = request.POST.get('first_name', '').strip()
        last_name       = request.POST.get('last_name', '').strip()
        username        = request.POST.get('username', '').strip()
        phone_number    = request.POST.get('phone_number', '').strip()
        profile_picture = request.FILES.get('profile_picture')
        enable_face     = request.POST.get('enable_face')
        cleaned_phone   = clean_phone_number(phone_number)
        if cleaned_phone and cleaned_phone != request.user.phone_number:
            if CustomUser.objects.filter(phone_number=cleaned_phone).exists():
                messages.error(request, "Este número de WhatsApp já está em uso.")
                return render(request, 'auth/profile.html')
        if username and username != request.user.username:
            if not re.match(r'^[\w.@+-]+$', username):
                messages.error(request, "Nome de usuário inválido. Use apenas letras, números e os caracteres . @ + - _")
                return render(request, 'auth/profile.html')
            if CustomUser.objects.filter(username__iexact=username).exclude(pk=request.user.pk).exists():
                messages.error(request, "Este nome de usuário já está em uso.")
                return render(request, 'auth/profile.html')
        try:
            user = request.user
            user.first_name = first_name
            user.last_name  = last_name
            if username:
                user.username = username
            if cleaned_phone:
                user.phone_number = cleaned_phone
            if profile_picture:
                user.profile_picture = profile_picture
            user.face_login_enabled = bool(enable_face)
            user.save()
            messages.success(request, "Perfil atualizado com sucesso!")
            if enable_face and not user.face_encoding:
                return redirect('face_register')
            return redirect('profile')
        except Exception as e:
            messages.error(request, f"Erro ao atualizar perfil: {e}")
    return render(request, 'auth/profile.html')


@login_required
def face_toggle_view(request):
    if request.method == 'POST':
        user = request.user
        user.face_login_enabled = not user.face_login_enabled
        if not user.face_login_enabled:
            user.face_encoding = None
        user.save()
        msg = "Reconhecimento facial ativado!" if user.face_login_enabled else "Reconhecimento facial desativado."
        messages.success(request, msg)
    return redirect('profile')