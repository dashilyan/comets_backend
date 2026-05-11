from django.urls import path
from . import views

urlpatterns = [
    # ── Аутентификация ────────────────────────────────────────────────────────
    path('api/register/', views.register_user, name='register'),
    path('api/login/', views.auth_login, name='login'),
    path('api/logout/', views.auth_logout, name='logout'),

    # ── Профиль ───────────────────────────────────────────────────────────────
    path('api/profile/', views.get_user_profile, name='profile'),
    path('api/profile/update/', views.update_user_profile, name='update_profile'),

    # ── Кометы ────────────────────────────────────────────────────────────────
    path('api/comets/', views.get_all_comets, name='all_comets'),
    path('api/comets/<int:comet_id>/', views.get_comet_detail, name='comet_detail'),

    # ── Телескопы ─────────────────────────────────────────────────────────────
    path('api/telescopes/', views.get_all_telescopes, name='all_telescopes'),
    path('api/telescopes/create/', views.create_telescope, name='create_telescope'),
    path('api/telescopes/find-or-create/', views.find_or_create_telescope, name='find_or_create_telescope'),

    # ── Наблюдения (фиксированные пути — до параметрических) ─────────────────
    path('api/observations/create/', views.create_observation, name='create_observation'),
    path('api/observations/my/', views.get_user_observations, name='user_observations'),
    path('api/observations/all/', views.get_all_observations, name='all_observations'),
    path('api/observations/<int:observation_id>/', views.get_observation_detail, name='observation_detail'),
    path('api/observations/<int:observation_id>/update/', views.update_observation, name='update_observation'),
    path('api/observations/<int:observation_id>/submit/', views.submit_observation, name='submit_observation'),

    # ── Избранное ─────────────────────────────────────────────────────────────
    path('api/favorites/', views.get_favorites, name='favorites'),
    path('api/favorites/add/<int:observation_id>/', views.add_to_favorites, name='add_favorite'),
    path('api/favorites/remove/<int:observation_id>/', views.remove_from_favorites, name='remove_favorite'),

    # ── Модерация ─────────────────────────────────────────────────────────────
    path('api/moderation/queue/', views.get_moderation_queue, name='moderation_queue'),
    path('api/moderation/approve/<int:observation_id>/', views.approve_observation, name='approve'),
    path('api/moderation/reject/<int:observation_id>/', views.reject_observation, name='reject'),

    # ── Распознавание YOLOv8 ──────────────────────────────────────────────────
    path('api/recognition/start/<int:observation_id>/', views.start_recognition, name='start_recognition'),
    path('api/recognition/results/<int:observation_id>/', views.get_recognition_results, name='recognition_results'),
]
