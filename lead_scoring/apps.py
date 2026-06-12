from django.apps import AppConfig


class LeadScoringConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'lead_scoring'
    verbose_name = 'Pontuação de Leads'

    def ready(self):
        import lead_scoring.signals  # noqa: F401
