"""Add snapshot fields for Google Place autocomplete.

Stores the place name, formatted address, and selection timestamp
so the frontend can display the linked business without calling Google.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0007_add_mode_and_trial_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='reviewconfig',
            name='google_place_name',
            field=models.CharField(
                blank=True,
                default='',
                max_length=255,
                help_text='Display name of the linked Google place.',
            ),
        ),
        migrations.AddField(
            model_name='reviewconfig',
            name='google_place_formatted_address',
            field=models.CharField(
                blank=True,
                default='',
                max_length=500,
                help_text='Formatted address of the linked Google place.',
            ),
        ),
        migrations.AddField(
            model_name='reviewconfig',
            name='google_place_updated_at',
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text='Timestamp of the last Google Place selection / update.',
            ),
        ),
    ]
