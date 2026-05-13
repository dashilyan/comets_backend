from rest_framework import serializers
from django.core.files.storage import default_storage
from django.contrib.auth.models import User

from .models import (
    Comet, Telescope, Observation, Calculation, Photo,
    UserProfile, UserFavorite, RecognitionTask, RecognitionResult,
)


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['education', 'city', 'bio', 'avatar_path']


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'date_joined', 'profile']


class UserStatsSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    total_observations = serializers.SerializerMethodField()
    public_observations = serializers.SerializerMethodField()
    calculations_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'date_joined', 'is_staff', 'profile',
            'total_observations', 'public_observations', 'calculations_count',
        ]

    def get_total_observations(self, obj):
        return obj.observation_set.count()

    def get_public_observations(self, obj):
        return obj.observation_set.filter(is_public=True).count()

    def get_calculations_count(self, obj):
        return Calculation.objects.filter(obs__user=obj).count()


class CometSerializer(serializers.ModelSerializer):
    first_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Comet
        fields = '__all__'

    def get_first_photo_url(self, obj):
        photo = Photo.objects.filter(obs__comet=obj, obs__status='published').first()
        if photo:
            try:
                return default_storage.url(photo.file_path)
            except Exception:
                return None
        return None


class TelescopeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Telescope
        fields = '__all__'


class PhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = Photo
        fields = ['id', 'file_name', 'file_path', 'url']

    def get_url(self, obj):
        try:
            return default_storage.url(obj.file_path)
        except Exception:
            return None


class CalculationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Calculation
        fields = '__all__'


class ObservationSerializer(serializers.ModelSerializer):
    comet_name = serializers.SerializerMethodField()
    telescope_model = serializers.CharField(source='telescope.model_name', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    photos_count = serializers.SerializerMethodField()
    first_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Observation
        fields = [
            'id', 'date_obs', 'coordinates', 'is_public', 'status',
            'date_created', 'comet_id', 'comet_name', 'telescope_id',
            'telescope_model', 'user_id', 'username', 'notes', 'photos_count',
            'first_photo_url',
        ]

    def get_comet_name(self, obj):
        return obj.comet.official_name if obj.comet_id else None

    def get_photos_count(self, obj):
        return obj.photos.count()

    def get_first_photo_url(self, obj):
        photo = obj.photos.first()
        if photo:
            try:
                return default_storage.url(photo.file_path)
            except Exception:
                return None
        return None


class ObservationDetailSerializer(serializers.ModelSerializer):
    comet = CometSerializer(read_only=True)
    telescope = TelescopeSerializer(read_only=True)
    user = UserSerializer(read_only=True)
    photos = PhotoSerializer(many=True, read_only=True)
    calculation = CalculationSerializer(read_only=True)
    recognition = serializers.SerializerMethodField()

    class Meta:
        model = Observation
        fields = '__all__'

    def get_recognition(self, obj):
        task = obj.recognition_tasks.filter(status='completed').order_by('-created_at').first()
        if not task:
            return None
        result = getattr(task, 'result', None)
        if not result:
            return None
        detections = []
        for det in (result.coordinates or []):
            recognized_url = None
            if det.get('recognized_path'):
                try:
                    recognized_url = default_storage.url(det['recognized_path'])
                except Exception:
                    pass
            detections.append({**det, 'recognized_url': recognized_url})
        return {
            'confidence': result.confidence,
            'recognized_at': result.recognized_at.isoformat() if result.recognized_at else None,
            'detections': detections,
        }


class UserFavoriteSerializer(serializers.ModelSerializer):
    observation = ObservationSerializer(read_only=True)

    class Meta:
        model = UserFavorite
        fields = ['id', 'observation', 'created_at']


class RecognitionResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecognitionResult
        fields = ['coordinates', 'confidence', 'recognized_at']


class RecognitionTaskSerializer(serializers.ModelSerializer):
    result = RecognitionResultSerializer(read_only=True)

    class Meta:
        model = RecognitionTask
        fields = ['id', 'task_id', 'status', 'created_at', 'result']
