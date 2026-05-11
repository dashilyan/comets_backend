import logging
import threading

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from .models import (
    Comet, Telescope, Observation, Calculation, Photo,
    UserProfile, UserFavorite, RecognitionTask, RecognitionResult,
)
from .serializers import (
    UserSerializer, UserStatsSerializer,
    ObservationSerializer, ObservationDetailSerializer,
    CometSerializer, TelescopeSerializer,
    PhotoSerializer, CalculationSerializer,
    UserFavoriteSerializer, RecognitionTaskSerializer,
)

logger = logging.getLogger(__name__)


# ==================== АУТЕНТИФИКАЦИЯ ====================

@api_view(['POST'])
def register_user(request):
    """Регистрация нового пользователя."""
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '')
    email = request.data.get('email', '')

    if not username or not password:
        return Response({'error': 'Логин и пароль обязательны'}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(username=username).exists():
        return Response({'error': 'Пользователь с таким логином уже существует'}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.create(
        username=username,
        email=email,
        password=make_password(password),
    )

    profile = user.profile  # создаётся сигналом
    profile.education = request.data.get('education', '')
    profile.city = request.data.get('city', '')
    profile.bio = request.data.get('bio', '')
    profile.save()

    return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def auth_login(request):
    """Вход в систему с сохранением сессии в Redis."""
    username = request.data.get('username')
    password = request.data.get('password')

    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response({'error': 'Неверный логин или пароль'}, status=status.HTTP_401_UNAUTHORIZED)

    login(request, user)
    return Response({'message': 'Успешная аутентификация', 'user': UserSerializer(user).data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def auth_logout(request):
    """Завершение сессии."""
    logout(request)
    return Response({'message': 'Вы успешно вышли из системы'})


# ==================== ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ ====================

@ensure_csrf_cookie
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_profile(request):
    """Профиль текущего пользователя со статистикой и последними наблюдениями."""
    user = request.user
    data = UserStatsSerializer(user).data
    data['recent_observations'] = ObservationSerializer(
        Observation.objects.filter(user=user).order_by('-date_obs')[:5],
        many=True,
    ).data
    return Response(data)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_user_profile(request):
    """Обновление профиля пользователя."""
    user = request.user
    for field in ('first_name', 'last_name', 'email'):
        if field in request.data:
            setattr(user, field, request.data[field])
    user.save()

    profile, _ = UserProfile.objects.get_or_create(user=user)
    for field in ('education', 'city', 'bio'):
        if field in request.data:
            setattr(profile, field, request.data[field])
    profile.save()

    return Response(UserSerializer(user).data)


# ==================== НАБЛЮДЕНИЯ ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_observation(request):
    """Создание наблюдения с загрузкой фото в MinIO и пересчётом avg-полей кометы."""
    try:
        telescope_id = request.data.get('telescope_id')
        comet_id = request.data.get('comet_id') or None  # опциональное поле

        if not telescope_id:
            return Response({'error': 'telescope_id обязателен'}, status=status.HTTP_400_BAD_REQUEST)

        photos = request.FILES.getlist('photos')
        if len(photos) < 3:
            return Response({'error': 'Необходимо загрузить минимум 3 фотографии'}, status=status.HTTP_400_BAD_REQUEST)

        observation = Observation.objects.create(
            date_obs=request.data.get('date_obs', timezone.now()),
            notes=request.data.get('notes', ''),
            coordinates=request.data.get('coordinates', ''),
            is_public=request.data.get('is_public', False),
            status='draft',
            user=request.user,
            comet_id=comet_id,
            telescope_id=telescope_id,
        )

        # Загрузка фото в MinIO
        for file in photos:
            key = f'observations/{observation.id}/{file.name}'
            saved_key = default_storage.save(key, ContentFile(file.read()))
            Photo.objects.create(file_path=saved_key, file_name=file.name, obs=observation)

        # Создание расчёта (пересчёт avg запускается сигналом post_save на Calculation)
        calc_fields = ['coma', 'brightness', 'axis', 'exentricity', 'inclination',
                       'longtitude', 'arg_perihelion', 'orbital_period']
        if any(request.data.get(f) is not None for f in calc_fields):
            Calculation.objects.create(
                coma=request.data.get('coma'),
                brightness=request.data.get('brightness'),
                axis=request.data.get('axis'),
                exentricity=request.data.get('exentricity'),
                inclination=request.data.get('inclination'),
                longtitude=request.data.get('longtitude'),
                arg_perihelion=request.data.get('arg_perihelion'),
                orbital_period=request.data.get('orbital_period'),
                obs=observation,
                comet_id=comet_id,
            )

        return Response(ObservationDetailSerializer(observation).data, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_observations(request):
    """Список наблюдений текущего пользователя с фильтрацией."""
    qs = Observation.objects.filter(user=request.user)

    comet_id = request.GET.get('comet_id')
    if comet_id:
        qs = qs.filter(comet_id=comet_id)

    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)

    date_from = request.GET.get('date_from')
    if date_from:
        qs = qs.filter(date_obs__gte=date_from)

    date_to = request.GET.get('date_to')
    if date_to:
        qs = qs.filter(date_obs__lte=date_to)

    ordering = request.GET.get('ordering', '-date_obs')
    if ordering in ('date_obs', '-date_obs', 'date_created', '-date_created'):
        qs = qs.order_by(ordering)

    return Response(ObservationSerializer(qs, many=True).data)


@api_view(['GET'])
def get_observation_detail(request, observation_id):
    """Детали конкретного наблюдения (только автор или публичное)."""
    try:
        observation = Observation.objects.get(pk=observation_id)
    except Observation.DoesNotExist:
        return Response({'error': 'Наблюдение не найдено'}, status=status.HTTP_404_NOT_FOUND)

    if not observation.is_public and (not request.user.is_authenticated or observation.user != request.user):
        return Response({'error': 'У вас нет доступа к этому наблюдению'}, status=status.HTTP_403_FORBIDDEN)

    return Response(ObservationDetailSerializer(observation).data)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_observation(request, observation_id):
    """Обновление черновика наблюдения (только автор, только пока статус draft)."""
    try:
        observation = Observation.objects.get(pk=observation_id, user=request.user)
    except Observation.DoesNotExist:
        return Response({'error': 'Наблюдение не найдено'}, status=status.HTTP_404_NOT_FOUND)

    if observation.status != 'draft':
        return Response({'error': 'Можно редактировать только черновики'}, status=status.HTTP_400_BAD_REQUEST)

    for field in ('notes', 'coordinates', 'is_public', 'date_obs'):
        if field in request.data:
            setattr(observation, field, request.data[field])
    observation.save()

    return Response(ObservationDetailSerializer(observation).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_observation(request, observation_id):
    """Отправка черновика на модерацию — меняет is_public=True, чтобы попасть в очередь."""
    try:
        observation = Observation.objects.get(pk=observation_id, user=request.user)
    except Observation.DoesNotExist:
        return Response({'error': 'Наблюдение не найдено'}, status=status.HTTP_404_NOT_FOUND)

    if observation.status != 'draft':
        return Response({'error': 'Можно отправить только черновик'}, status=status.HTTP_400_BAD_REQUEST)

    # Статус остаётся draft до одобрения модератором,
    # но is_public=False — наблюдение видно только в очереди модерации.
    observation.is_public = False
    observation.save(update_fields=['is_public'])

    return Response({'message': 'Наблюдение отправлено на модерацию', 'id': observation.id})


# ==================== КОМЕТЫ ====================

@api_view(['GET'])
def get_all_comets(request):
    """Каталог комет с фильтрацией по яркости и поиском по названию."""
    qs = Comet.objects.all()

    min_brightness = request.GET.get('min_brightness')
    if min_brightness:
        qs = qs.filter(brightness__gte=min_brightness)

    max_brightness = request.GET.get('max_brightness')
    if max_brightness:
        qs = qs.filter(brightness__lte=max_brightness)

    search = request.GET.get('search')
    if search:
        qs = qs.filter(official_name__icontains=search)

    return Response(CometSerializer(qs, many=True).data)


@api_view(['GET'])
def get_comet_detail(request, comet_id):
    """
    Детали кометы. Avg-поля (a_avg, e_avg, brightness и т.д.) хранятся
    непосредственно в модели Comet и пересчитываются сигналом при каждом
    сохранении/удалении Calculation.
    """
    try:
        comet = Comet.objects.get(pk=comet_id)
    except Comet.DoesNotExist:
        return Response({'error': 'Комета не найдена'}, status=status.HTTP_404_NOT_FOUND)

    observations = Observation.objects.filter(comet=comet, is_public=True)

    data = CometSerializer(comet).data
    data['observations_count'] = observations.count()
    data['observations'] = ObservationSerializer(observations, many=True).data

    return Response(data)


# ==================== ВСЕ НАБЛЮДЕНИЯ (КАТАЛОГ) ====================

@api_view(['GET'])
def get_all_observations(request):
    """Публичный каталог наблюдений с фильтрацией и пагинацией."""
    qs = Observation.objects.filter(is_public=True, status='published').select_related('comet', 'telescope', 'user')

    comet_id = request.GET.get('comet_id')
    if comet_id:
        qs = qs.filter(comet_id=comet_id)

    username = request.GET.get('username')
    if username:
        qs = qs.filter(user__username=username)

    comet_search = request.GET.get('comet_search')
    if comet_search:
        qs = qs.filter(comet__official_name__icontains=comet_search)

    date_from = request.GET.get('date_from')
    if date_from:
        qs = qs.filter(date_obs__gte=date_from)

    date_to = request.GET.get('date_to')
    if date_to:
        qs = qs.filter(date_obs__lte=date_to)

    search = request.GET.get('search')
    if search:
        qs = qs.filter(notes__icontains=search)

    total = qs.count()
    limit = min(int(request.GET.get('limit', 20)), 100)
    offset = int(request.GET.get('offset', 0))

    return Response({
        'total': total,
        'limit': limit,
        'offset': offset,
        'observations': ObservationSerializer(qs[offset:offset + limit], many=True).data,
    })


# ==================== ТЕЛЕСКОПЫ ====================

@api_view(['GET'])
def get_all_telescopes(request):
    """Список всех телескопов."""
    qs = Telescope.objects.all()
    search = request.GET.get('search')
    if search:
        qs = qs.filter(model_name__icontains=search)
    return Response(TelescopeSerializer(qs, many=True).data)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def create_telescope(request):
    """Добавление нового телескопа (только администратор)."""
    serializer = TelescopeSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def find_or_create_telescope(request):
    """Найти телескоп по model_name или создать новый (доступно всем авторизованным)."""
    model_name = (request.data.get('model_name') or '').strip()
    if not model_name:
        return Response({'error': 'model_name обязателен'}, status=status.HTTP_400_BAD_REQUEST)

    focal_length = request.data.get('focal_length')
    manufacturer = request.data.get('manufacturer') or None

    telescope, created = Telescope.objects.get_or_create(
        model_name=model_name,
        defaults={
            'focal_length': focal_length,
            'manufacturer': manufacturer,
        },
    )
    return Response(
        TelescopeSerializer(telescope).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


# ==================== ИЗБРАННОЕ ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_favorites(request):
    """Список избранных наблюдений текущего пользователя."""
    favorites = UserFavorite.objects.filter(user=request.user).select_related('observation')
    return Response(UserFavoriteSerializer(favorites, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_to_favorites(request, observation_id):
    """Добавить наблюдение в избранное."""
    try:
        observation = Observation.objects.get(pk=observation_id)
    except Observation.DoesNotExist:
        return Response({'error': 'Наблюдение не найдено'}, status=status.HTTP_404_NOT_FOUND)

    _, created = UserFavorite.objects.get_or_create(user=request.user, observation=observation)
    if not created:
        return Response({'message': 'Уже в избранном'}, status=status.HTTP_200_OK)
    return Response({'message': 'Наблюдение добавлено в избранное'}, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_from_favorites(request, observation_id):
    """Удалить наблюдение из избранного."""
    deleted, _ = UserFavorite.objects.filter(user=request.user, observation_id=observation_id).delete()
    if not deleted:
        return Response({'error': 'Наблюдение не найдено в избранном'}, status=status.HTTP_404_NOT_FOUND)
    return Response({'message': 'Наблюдение удалено из избранного'})


# ==================== МОДЕРАЦИЯ ====================

@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_moderation_queue(request):
    """Очередь на модерацию: все наблюдения со статусом draft."""
    qs = Observation.objects.filter(status='draft')

    date_from = request.GET.get('date_from')
    if date_from:
        qs = qs.filter(date_obs__gte=date_from)

    date_to = request.GET.get('date_to')
    if date_to:
        qs = qs.filter(date_obs__lte=date_to)

    return Response({
        'total': qs.count(),
        'observations': ObservationDetailSerializer(qs, many=True).data,
    })


@api_view(['PUT'])
@permission_classes([IsAdminUser])
def approve_observation(request, observation_id):
    """Одобрить наблюдение → статус published, is_public=True."""
    try:
        observation = Observation.objects.get(pk=observation_id)
    except Observation.DoesNotExist:
        return Response({'error': 'Наблюдение не найдено'}, status=status.HTTP_404_NOT_FOUND)

    observation.status = 'published'
    observation.is_public = True
    observation.save(update_fields=['status', 'is_public'])
    return Response({'message': 'Наблюдение опубликовано'})


@api_view(['PUT'])
@permission_classes([IsAdminUser])
def reject_observation(request, observation_id):
    """Отклонить наблюдение → статус rejected."""
    try:
        observation = Observation.objects.get(pk=observation_id)
    except Observation.DoesNotExist:
        return Response({'error': 'Наблюдение не найдено'}, status=status.HTTP_404_NOT_FOUND)

    observation.status = 'rejected'
    observation.is_public = False
    observation.save(update_fields=['status', 'is_public'])
    return Response({'message': 'Наблюдение отклонено'})


# ==================== РАСПОЗНАВАНИЕ И РАСЧЁТ ОРБИТЫ ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_recognition(request, observation_id):
    """
    Запуск пайплайна: ONNX-детекция кометы на каждом фото наблюдения,
    перевод пиксельных координат в экваториальные (RA/Dec), вычисление
    орбитальных параметров (a, e, i, Ω, ω, T) и сохранение в Calculation.

    Возвращает 202 немедленно; вычисления выполняются в фоновом потоке.
    Статус и результаты доступны через GET /observations/{id}/recognition/.
    """
    try:
        observation = Observation.objects.get(pk=observation_id, user=request.user)
    except Observation.DoesNotExist:
        return Response({'error': 'Наблюдение не найдено'}, status=status.HTTP_404_NOT_FOUND)

    if not observation.photos.exists():
        return Response({'error': 'У наблюдения нет фотографий'}, status=status.HTTP_400_BAD_REQUEST)

    if not observation.telescope.focal_length:
        return Response(
            {'error': 'У телескопа не указана фокусная длина — необходима для астрометрии'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    from .services.pipeline import run_pipeline

    def _run_bg():
        try:
            run_pipeline(observation_id)
        except Exception as exc:
            logger.exception("Background pipeline error for observation %d: %s", observation_id, exc)

    thread = threading.Thread(target=_run_bg, daemon=True)
    thread.start()

    # Возвращаем последний созданный task (run_pipeline создаёт его сам),
    # но он может ещё не существовать в момент ответа — возвращаем статус-объект.
    task = observation.recognition_tasks.order_by('-created_at').first()
    if task:
        return Response(RecognitionTaskSerializer(task).data, status=status.HTTP_202_ACCEPTED)
    return Response({'message': 'Пайплайн запущен'}, status=status.HTTP_202_ACCEPTED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recognition_results(request, observation_id):
    """Результаты последней задачи распознавания для наблюдения."""
    try:
        observation = Observation.objects.get(pk=observation_id)
    except Observation.DoesNotExist:
        return Response({'error': 'Наблюдение не найдено'}, status=status.HTTP_404_NOT_FOUND)

    if not observation.is_public and observation.user != request.user:
        return Response({'error': 'Доступ запрещён'}, status=status.HTTP_403_FORBIDDEN)

    task = observation.recognition_tasks.order_by('-created_at').first()
    if task is None:
        return Response({'message': 'Задача распознавания не запускалась'}, status=status.HTTP_404_NOT_FOUND)

    return Response(RecognitionTaskSerializer(task).data)
