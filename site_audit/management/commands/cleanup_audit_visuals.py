from django.core.management.base import BaseCommand
from django.utils import timezone

from site_audit.models import SiteAuditVisualAsset


class Command(BaseCommand):
    help = 'Remove arquivos e registros de evidências visuais de auditoria expirados (TTL 24h).'

    def handle(self, *args, **options):
        now = timezone.now()
        expired = SiteAuditVisualAsset.objects.filter(expires_at__lt=now)
        count = expired.count()
        for asset in expired.iterator():
            try:
                if asset.file:
                    from pathlib import Path
                    from django.conf import settings
                    path = Path(settings.MEDIA_ROOT) / asset.file
                    if path.exists():
                        path.unlink()
                    webp = path.with_suffix('.webp')
                    if webp.exists():
                        webp.unlink()
            except OSError:
                pass
            asset.delete()
        self.stdout.write(self.style.SUCCESS(f'Removidos {count} asset(s) expirado(s).'))
