"""
Migrate ReviewStatus choices from pending/reviewed/archived to new/read/contacted/resolved.
"""

from django.db import migrations


def migrate_statuses_forward(apps, schema_editor):
    Review = apps.get_model('reviews', 'Review')
    # Map old values to new values
    Review.objects.filter(status='pending').update(status='new')
    Review.objects.filter(status='reviewed').update(status='read')
    Review.objects.filter(status='archived').update(status='resolved')


def migrate_statuses_backward(apps, schema_editor):
    Review = apps.get_model('reviews', 'Review')
    Review.objects.filter(status='new').update(status='pending')
    Review.objects.filter(status='read').update(status='reviewed')
    Review.objects.filter(status='contacted').update(status='reviewed')
    Review.objects.filter(status='resolved').update(status='archived')


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0002_migrate_engagement_data'),
    ]

    operations = [
        migrations.RunPython(migrate_statuses_forward, migrate_statuses_backward),
    ]
