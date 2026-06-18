"""Sincroniza perfis faciais entre o banco e os arquivos versionáveis.

Uso:
  python manage.py sync_faces                # restaura arquivos -> banco (sem sobrescrever)
  python manage.py sync_faces --overwrite    # restaura e sobrescreve o que já existe
  python manage.py sync_faces --export       # exporta banco -> arquivos
"""
from django.core.management.base import BaseCommand

from authentication.face_store import export_all, import_profiles


class Command(BaseCommand):
    help = 'Importa/exporta perfis faciais entre o banco e arquivos versionáveis.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--export', action='store_true',
            help='Exporta os perfis do banco para arquivos.',
        )
        parser.add_argument(
            '--overwrite', action='store_true',
            help='Ao importar, sobrescreve perfis já existentes no banco.',
        )

    def handle(self, *args, **options):
        if options['export']:
            count = export_all()
            self.stdout.write(self.style.SUCCESS(
                f'{count} perfil(is) facial(is) exportado(s) para arquivo.'
            ))
            return

        restored, files = import_profiles(overwrite=options['overwrite'])
        self.stdout.write(self.style.SUCCESS(
            f'{restored} perfil(is) restaurado(s) de {files} arquivo(s).'
        ))
