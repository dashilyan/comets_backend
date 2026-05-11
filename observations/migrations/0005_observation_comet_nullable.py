import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0004_photo_taken_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='observation',
            name='comet',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='observations.comet',
            ),
        ),
    ]
