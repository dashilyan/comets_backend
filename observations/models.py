from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    education = models.CharField(max_length=256, blank=True, default='')
    city = models.CharField(max_length=128, blank=True, default='')
    bio = models.TextField(blank=True, default='')
    avatar_path = models.CharField(max_length=512, blank=True, default='')

    class Meta:
        db_table = 'user_profiles'

    def __str__(self):
        return f"Profile of {self.user.username}"


class Comet(models.Model):
    official_name = models.CharField(max_length=128, null=False)
    date_founded = models.DateTimeField(null=True, blank=True)
    a_avg = models.FloatField(null=True, blank=True)      # большая полуось
    e_avg = models.FloatField(null=True, blank=True)      # эксцентриситет
    i_avg = models.FloatField(null=True, blank=True)      # наклонение
    node_avg = models.FloatField(null=True, blank=True)   # долгота восходящего узла
    peri_avg = models.FloatField(null=True, blank=True)   # аргумент перигелия
    p_avg = models.FloatField(null=True, blank=True)      # период обращения
    coma_size = models.CharField(max_length=128, null=True, blank=True)
    brightness = models.FloatField(null=True, blank=True)  # среднее из наблюдений

    class Meta:
        managed = True
        db_table = 'comets'

    def __str__(self):
        return self.official_name


class Telescope(models.Model):
    model_name = models.CharField(max_length=128, unique=True, null=False)
    focal_length = models.FloatField(null=True, blank=True)
    manufacturer = models.CharField(max_length=128, null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'telescopes'

    def __str__(self):
        return self.model_name


class Observation(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('rejected', 'Rejected'),
        ('archived', 'Archived'),
    ]

    date_obs = models.DateTimeField(null=False)
    notes = models.TextField(null=True, blank=True)
    coordinates = models.CharField(max_length=32, null=False)
    is_public = models.BooleanField(default=False)
    date_created = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=16, null=False, choices=STATUS_CHOICES, default='draft')

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=False)
    comet = models.ForeignKey(Comet, on_delete=models.SET_NULL, null=True, blank=True)
    telescope = models.ForeignKey(Telescope, on_delete=models.RESTRICT, null=False)

    class Meta:
        managed = True
        db_table = 'observations'

    def __str__(self):
        return f"Observation #{self.id} - {self.comet.official_name} - {self.date_obs}"


class Calculation(models.Model):
    coma = models.CharField(max_length=128, null=True, blank=True)
    brightness = models.IntegerField(null=True, blank=True)
    axis = models.FloatField(null=True, blank=True)          # большая полуось
    exentricity = models.FloatField(null=True, blank=True)   # эксцентриситет (имя из схемы БД)
    inclination = models.FloatField(null=True, blank=True)   # наклонение
    longtitude = models.FloatField(null=True, blank=True)    # долгота восходящего узла (имя из схемы)
    arg_perihelion = models.FloatField(null=True, blank=True)
    orbital_period = models.FloatField(null=True, blank=True)

    obs = models.OneToOneField(Observation, on_delete=models.CASCADE, null=False, related_name='calculation')
    comet = models.ForeignKey(Comet, on_delete=models.RESTRICT, null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'calculations'

    def __str__(self):
        return f"Calculation for Observation #{self.obs_id}"


class Photo(models.Model):
    # file_path хранит ключ объекта в MinIO (относительный путь внутри бакета)
    file_path = models.CharField(max_length=512, null=False)
    file_name = models.CharField(max_length=256, null=False)
    taken_at = models.DateTimeField(null=True, blank=True)  # время съёмки кадра
    obs = models.ForeignKey(Observation, on_delete=models.CASCADE, null=False, related_name='photos')

    class Meta:
        managed = True
        db_table = 'photos'

    def __str__(self):
        return self.file_name


class UserFavorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    observation = models.ForeignKey(Observation, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_favorites'
        unique_together = [('user', 'observation')]

    def __str__(self):
        return f"{self.user.username} → obs#{self.observation_id}"


class RecognitionTask(models.Model):
    STATUS_CHOICES = [
        ('started', 'Started'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    observation = models.ForeignKey(Observation, on_delete=models.CASCADE, related_name='recognition_tasks')
    task_id = models.CharField(max_length=128, unique=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='started')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'recognition_tasks'

    def __str__(self):
        return f"Task {self.task_id} [{self.status}]"


class RecognitionResult(models.Model):
    task = models.OneToOneField(RecognitionTask, on_delete=models.CASCADE, related_name='result')
    coordinates = models.JSONField()
    confidence = models.FloatField()
    recognized_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'recognition_results'

    def __str__(self):
        return f"Result for task {self.task_id}"
