from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Avg
from django.contrib.auth.models import User

from .models import Calculation, UserProfile


def update_comet_averages(comet_id):
    """Пересчитывает avg-поля кометы по всем связанным расчётам наблюдений."""
    from .models import Comet

    averages = Calculation.objects.filter(comet_id=comet_id).aggregate(
        a_avg=Avg('axis'),
        e_avg=Avg('exentricity'),
        i_avg=Avg('inclination'),
        node_avg=Avg('longtitude'),
        peri_avg=Avg('arg_perihelion'),
        p_avg=Avg('orbital_period'),
        brightness=Avg('brightness'),
    )
    Comet.objects.filter(pk=comet_id).update(**averages)


@receiver(post_save, sender=Calculation)
def on_calculation_save(sender, instance, **kwargs):
    update_comet_averages(instance.comet_id)


@receiver(post_delete, sender=Calculation)
def on_calculation_delete(sender, instance, **kwargs):
    update_comet_averages(instance.comet_id)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
