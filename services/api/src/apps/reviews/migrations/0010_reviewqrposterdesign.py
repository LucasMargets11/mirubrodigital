# Generated 2026-05-11

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import common.storages


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0009_add_ip_hash_to_reviewvisit'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ReviewQrPosterDesign',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('payload', models.JSONField(help_text='Poster configuration excluding background_image file.')),
                ('background_image', models.ImageField(
                    blank=True,
                    help_text='Optional background image (JPG/PNG, max 10 MB).',
                    null=True,
                    storage=common.storages.public_media_storage,
                    upload_to='reviews/poster_designs/',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='qr_poster_designs',
                    to='business.business',
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'QR Poster Design',
                'verbose_name_plural': 'QR Poster Designs',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='reviewqrposterdesign',
            index=models.Index(fields=['business', '-updated_at'], name='reviews_rev_busines_updated_idx'),
        ),
    ]
