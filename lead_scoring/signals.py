from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import ScoringCondition, ScoringRule
from .recalculate import recalculate_all_leads


@receiver(post_save, sender=ScoringRule)
@receiver(post_delete, sender=ScoringRule)
@receiver(post_save, sender=ScoringCondition)
@receiver(post_delete, sender=ScoringCondition)
def trigger_recalculate_on_rule_change(sender, **kwargs):
    recalculate_all_leads()
