import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0002_alter_observation_date_created'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Исправить default у date_created — использовать timezone.now (callable)
        migrations.AlterField(
            model_name='observation',
            name='date_created',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),

        # 2. Исправить тип brightness у Comet (int → float для avg)
        migrations.AlterField(
            model_name='comet',
            name='brightness',
            field=models.FloatField(blank=True, null=True),
        ),

        # 3. Добавить статус 'rejected' в Observation
        migrations.AlterField(
            model_name='observation',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('published', 'Published'),
                    ('rejected', 'Rejected'),
                    ('archived', 'Archived'),
                ],
                default='draft',
                max_length=16,
            ),
        ),

        # 4. Расширить file_path в Photo (256 → 512)
        migrations.AlterField(
            model_name='photo',
            name='file_path',
            field=models.CharField(max_length=512),
        ),

        # 5. Добавить related_name к Photo.obs
        migrations.AlterField(
            model_name='photo',
            name='obs',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='photos',
                to='observations.observation',
            ),
        ),

        # 6. Добавить related_name к Calculation.obs
        migrations.AlterField(
            model_name='calculation',
            name='obs',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='calculation',
                to='observations.observation',
            ),
        ),

        # 7. UserProfile
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('education', models.CharField(blank=True, default='', max_length=256)),
                ('city', models.CharField(blank=True, default='', max_length=128)),
                ('bio', models.TextField(blank=True, default='')),
                ('avatar_path', models.CharField(blank=True, default='', max_length=512)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='profile',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'db_table': 'user_profiles'},
        ),

        # 8. UserFavorite
        migrations.CreateModel(
            name='UserFavorite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='favorites',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('observation', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='favorited_by',
                    to='observations.observation',
                )),
            ],
            options={'db_table': 'user_favorites'},
        ),
        migrations.AddConstraint(
            model_name='userfavorite',
            constraint=models.UniqueConstraint(fields=['user', 'observation'], name='unique_user_favorite'),
        ),

        # 9. RecognitionTask
        migrations.CreateModel(
            name='RecognitionTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('task_id', models.CharField(max_length=128, unique=True)),
                ('status', models.CharField(
                    choices=[
                        ('started', 'Started'),
                        ('processing', 'Processing'),
                        ('completed', 'Completed'),
                        ('failed', 'Failed'),
                    ],
                    default='started',
                    max_length=16,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('observation', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='recognition_tasks',
                    to='observations.observation',
                )),
            ],
            options={'db_table': 'recognition_tasks'},
        ),

        # 10. RecognitionResult
        migrations.CreateModel(
            name='RecognitionResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('coordinates', models.JSONField()),
                ('confidence', models.FloatField()),
                ('recognized_at', models.DateTimeField(auto_now_add=True)),
                ('task', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='result',
                    to='observations.recognitiontask',
                )),
            ],
            options={'db_table': 'recognition_results'},
        ),
    ]
