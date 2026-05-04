"""
0015 — Add sort_order and cta_label fields to Bundle.

sort_order: integer used to control visual display order within a vertical.
cta_label:  per-plan CTA button text shown on plan cards.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0014_add_qr_reviews_pro_plan'),
    ]

    operations = [
        migrations.AddField(
            model_name='bundle',
            name='sort_order',
            field=models.IntegerField(
                default=0,
                help_text='Visual display order within a vertical (lower = first)',
            ),
        ),
        migrations.AddField(
            model_name='bundle',
            name='cta_label',
            field=models.CharField(
                blank=True,
                default='',
                max_length=128,
                help_text='CTA button label for plan card',
            ),
        ),
    ]
