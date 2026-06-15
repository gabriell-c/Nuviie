from django.core.management.base import BaseCommand

from notifications.services import check_deadline_notifications


class Command(BaseCommand):
    help = 'Verifica prazos de projetos e cria notificações'

    def handle(self, *args, **options):
        n = check_deadline_notifications()
        self.stdout.write(self.style.SUCCESS(f'{n} notificação(ões) criada(s).'))
