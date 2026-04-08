"""
Update Review.status field choices and default to match new ReviewStatus enum.
"""

import django.db.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0003_update_review_statuses'),
    ]

    operations = [
        migrations.AlterField(
            model_name='review',
            name='status',
            field=models.CharField(
                choices=[('new', 'Nuevo'), ('read', 'Leído'), ('contacted', 'Contactado'), ('resolved', 'Resuelto')],
                default='new',
                max_length=16,
            ),
        ),
    ]
