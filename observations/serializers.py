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
            'date_joined', 'profile',
            'total_observations', 'public_observations', 'calculations_count',
        ]

    def get_total_observations(self, obj):
        return obj.observation_set.count()

    def get_public_observations(self, obj):
        return obj.observation_set.filter(is_public=True).count()

    def get_calculations_count(self, obj):
        return Calculation.objects.filter(obs__user=obj).count()


class CometSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comet
        fields = '__all__'


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
    comet_name = serializers.CharField(source='comet.official_name', read_only=True)
    telescope_model = serializers.CharField(source='telescope.model_name', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    photos_count = serializers.SerializerMethodField()

    class Meta:
        model = Observation
        fields = [
            'id', 'date_obs', 'coordinates', 'is_public', 'status',
            'date_created', 'comet_id', 'comet_name', 'telescope_id',
            'telescope_model', 'user_id', 'username', 'notes', 'photos_count',
        ]

    def get_photos_count(self, obj):
        return obj.photos.count()


class ObservationDetailSerializer(serializers.ModelSerializer):
    comet = CometSerializer(read_only=True)
    telescope = TelescopeSerializer(read_only=True)
    user = UserSerializer(read_only=True)
    photos = PhotoSerializer(many=True, read_only=True)
    calculation = CalculationSerializer(read_only=True)

    class Meta:
        model = Observation
        fields = '__all__'


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
