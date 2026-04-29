from django.contrib import admin
from .models import (
    Comet, Telescope, Observation, Calculation, Photo,
    UserProfile, UserFavorite, RecognitionTask, RecognitionResult,
)


@admin.register(Comet)
class CometAdmin(admin.ModelAdmin):
    list_display = ['official_name', 'date_founded', 'brightness', 'a_avg', 'e_avg', 'p_avg']
    search_fields = ['official_name']
    list_filter = ['date_founded']


@admin.register(Telescope)
class TelescopeAdmin(admin.ModelAdmin):
    list_display = ['model_name', 'manufacturer', 'focal_length']
    search_fields = ['model_name', 'manufacturer']


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 0
    readonly_fields = ['file_name', 'file_path']


class CalculationInline(admin.StackedInline):
    model = Calculation
    extra = 0


@admin.register(Observation)
class ObservationAdmin(admin.ModelAdmin):
    list_display = ['id', 'comet', 'user', 'date_obs', 'status', 'is_public', 'date_created']
    list_filter = ['status', 'is_public', 'comet']
    search_fields = ['user__username', 'comet__official_name', 'notes']
    readonly_fields = ['date_created']
    inlines = [PhotoInline, CalculationInline]
    actions = ['approve_selected', 'reject_selected']

    @admin.action(description='Опубликовать выбранные наблюдения')
    def approve_selected(self, request, queryset):
        queryset.update(status='published', is_public=True)

    @admin.action(description='Отклонить выбранные наблюдения')
    def reject_selected(self, request, queryset):
        queryset.update(status='rejected', is_public=False)


@admin.register(Calculation)
class CalculationAdmin(admin.ModelAdmin):
    list_display = ['id', 'obs', 'comet', 'brightness', 'axis', 'exentricity', 'orbital_period']
    list_select_related = ['obs', 'comet']


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ['id', 'file_name', 'obs']
    search_fields = ['file_name']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'education', 'city']
    search_fields = ['user__username', 'city']


@admin.register(UserFavorite)
class UserFavoriteAdmin(admin.ModelAdmin):
    list_display = ['user', 'observation', 'created_at']
    list_filter = ['created_at']


@admin.register(RecognitionTask)
class RecognitionTaskAdmin(admin.ModelAdmin):
    list_display = ['task_id', 'observation', 'status', 'created_at']
    list_filter = ['status']


@admin.register(RecognitionResult)
class RecognitionResultAdmin(admin.ModelAdmin):
    list_display = ['task', 'confidence', 'recognized_at']
