from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0009_rename_menu_layout_business_position_idx_menu_menula_busines_32faae_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='menucategory',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='menu/categories/'),
        ),
        migrations.AddField(
            model_name='menucategory',
            name='image_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
