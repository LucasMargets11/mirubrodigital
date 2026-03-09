# Phase 2A – Data migration: populate Business.slug and Business.service_type
# 
# slug: generated from business name (slugified) with collision handling.
#       Existing rows will have deterministic, unique slugs after this migration.
# service_type: copied verbatim from default_service (identical value space).
#
# RISK: RunPython locks rows one at a time. For large datasets (>10k businesses),
#       consider batching. Typical SaaS installation will have < 1000 businesses.
# ROLLBACK: reverse function is a no-op (slugs left in place if rolled back).

from django.db import migrations
from django.utils.text import slugify


def populate_slug_and_service_type(apps, schema_editor):
    Business = apps.get_model('business', 'Business')

    for business in Business.objects.filter(slug__isnull=True).order_by('id'):
        base = slugify(business.name) or f'negocio-{str(business.pk)[:8]}'
        base = base[:80]
        slug = base
        counter = 1
        while Business.objects.filter(slug=slug).exists():
            suffix = f'-{counter}'
            slug = f'{base[:80 - len(suffix)]}{suffix}'
            counter += 1

        # service_type mirrors default_service – same value space
        service_type = getattr(business, 'default_service', None) or None

        business.slug = slug
        business.service_type = service_type
        business.save(update_fields=['slug', 'service_type'])


def reverse_noop(apps, schema_editor):
    pass  # Intentionally irreversible; slugs can stay if migration is reversed.


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0015_phase2a_business_extend'),
    ]

    operations = [
        migrations.RunPython(populate_slug_and_service_type, reverse_noop),
    ]
