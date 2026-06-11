"""
Django settings for core project.
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ── Carrega variáveis do .env ────────────────────────────────────────────────
# Suporta python-dotenv (pip install python-dotenv) ou django-environ.
# Se nenhum estiver instalado, lê o .env manualmente como fallback.
def _load_env(base_dir):
    env_path = base_dir / '.env'
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
        return
    except ImportError:
        pass
    # Fallback manual — funciona sem dependências extras
    with open(env_path, encoding='utf-8') as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith('#') or '=' not in _line:
                continue
            _key, _, _val = _line.partition('=')
            _key = _key.strip()
            _val = _val.strip().strip('"').strip("'")
            if _key and _key not in os.environ:
                os.environ[_key] = _val

_load_env(BASE_DIR)


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, '').strip().lower()
    if not val:
        return default
    return val in ('1', 'true', 'yes', 'on')


def _env_list(key: str, default: list[str] | None = None) -> list[str]:
    raw = os.environ.get(key, '').strip()
    if not raw:
        return default or []
    return [item.strip() for item in raw.split(',') if item.strip()]


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-dev-only-change-in-production',
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = _env_bool('DEBUG', default=True)

ALLOWED_HOSTS = _env_list('ALLOWED_HOSTS', default=['127.0.0.1', 'localhost'])


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party apps
    'rest_framework',
    'corsheaders',

    # Nuviie SaaS apps
    'authentication',
    'leads',
    'contracts',
    'chat',
    'audit',
    'monitoring',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # WhiteNoise for static files
    'corsheaders.middleware.CorsMiddleware',       # CORS support
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'pt-br'

TIME_ZONE = 'America/Sao_Paulo'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

NUVIIE_PUBLIC_BASE_URL = os.environ.get('NUVIIE_PUBLIC_BASE_URL', 'http://127.0.0.1:8000')

# Custom Auth Model
AUTH_USER_MODEL = 'authentication.CustomUser'

# Django REST Framework configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# CORS Configuration
_cors_origins = _env_list('CORS_ALLOWED_ORIGINS')
if _cors_origins:
    CORS_ALLOWED_ORIGINS = _cors_origins
    CORS_ALLOW_ALL_ORIGINS = False
else:
    CORS_ALLOW_ALL_ORIGINS = _env_bool('CORS_ALLOW_ALL_ORIGINS', default=DEBUG)

CORS_ALLOWED_ORIGIN_REGEXES = [
    r'^chrome-extension://.*$',
]

# ── Extensão Chrome Maps Extractor ───────────────────────────────────────────
NUVIIE_EXTENSION_TOKEN = os.environ.get('NUVIIE_EXTENSION_TOKEN', '')
NUVIIE_EXTENSION_USER  = os.environ.get('NUVIIE_EXTENSION_USER', 'admin')
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

# ── Integrações externas ─────────────────────────────────────────────────────
EVOLUTION_API_URL      = os.environ.get('EVOLUTION_API_URL', '')
EVOLUTION_API_KEY      = os.environ.get('EVOLUTION_API_KEY', '')
EVOLUTION_INSTANCE     = os.environ.get('EVOLUTION_INSTANCE', '')
OLLAMA_URL             = os.environ.get('OLLAMA_URL', 'http://localhost:11434/api/chat')
OLLAMA_MODEL           = os.environ.get('OLLAMA_MODEL', 'qwen2.5:7b')

# ── Playwright / Scraper ─────────────────────────────────────────────────────
PLAYWRIGHT_BROWSERS_PATH = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '')
MAPS_SCRAPER_TIMEOUT     = int(os.environ.get('MAPS_SCRAPER_TIMEOUT', 600))
NUVIIE_SCREENSHOT_DIR    = os.environ.get('NUVIIE_SCREENSHOT_DIR', '')

# Propaga PLAYWRIGHT_BROWSERS_PATH para subprocessos lançados pelo Django
if PLAYWRIGHT_BROWSERS_PATH:
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = PLAYWRIGHT_BROWSERS_PATH

# ── Logging ──────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        # Scraper — mostra todos os logs do Playwright e do runner
        'leads': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'leads.scraper': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'runner': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        # Django — mantém apenas WARNING para não poluir
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}