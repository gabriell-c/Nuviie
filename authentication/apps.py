import logging
import os
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AuthenticationConfig(AppConfig):
    name = 'authentication'

    def ready(self):
        # Evita rodar duas vezes com o autoreloader do runserver.
        if os.environ.get('RUN_MAIN') == 'false':
            return

        def _restore():
            try:
                from .face_store import import_profiles
                restored, _ = import_profiles()
                if restored:
                    logger.info('Perfis faciais restaurados no boot: %d', restored)
            except Exception:
                # Banco pode ainda não estar migrado (ex.: durante migrate). Ignora.
                logger.debug('Restauração de perfis faciais adiada/ignorada', exc_info=True)

        # Em background para não atrasar o startup nem quebrar comandos como migrate.
        threading.Thread(target=_restore, daemon=True).start()
