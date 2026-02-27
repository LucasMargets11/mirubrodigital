from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0004_menubrandingsettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='menuitem',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='menu/items/'),
        ),
        migrations.AddField(
            model_name='menuitem',
            name='image_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
