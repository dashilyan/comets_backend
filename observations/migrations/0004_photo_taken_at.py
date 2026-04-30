from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0003_add_new_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='photo',
            name='taken_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
