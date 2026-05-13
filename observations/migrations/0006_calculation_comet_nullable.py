import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0005_observation_comet_nullable'),
        ('observations', '0005_remove_userfavorite_unique_user_favorite_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='calculation',
            name='comet',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                to='observations.comet',
            ),
        ),
    ]
