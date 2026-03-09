# Phase 2A – Business model extension
# Adds: slug, service_type, country, currency, timezone,
#        trial_starts_at, trial_ends_at, activated_at, suspended_at, updated_at
#        + status/parent indexes
# NOTE: slug is nullable here. A data migration (0016) populates values.
#       A constraint (baked into Meta) is applied in this same migration via AddConstraint.
# RISK: AddField with defaults is non-locking in PostgreSQL 11+. Safe for production.
# RISK: updated_at (auto_now) on existing rows will receive the migration timestamp – acceptable.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0014_menu_qr_plans_pro_module'),
    ]

    operations = [
        # ── New fields ──────────────────────────────────────────────────────
        migrations.AddField(
            model_name='business',
            name='slug',
            field=models.SlugField(
                max_length=80,
                null=True,
                blank=True,
                help_text='URL-friendly identifier. Populated by data migration 0016.',
            ),
        ),
        migrations.AddField(
            model_name='business',
            name='service_type',
            field=models.CharField(
                max_length=32,
                null=True,
                blank=True,
                choices=[
                    ('gestion',       'Gestión Comercial'),
                    ('restaurante',   'Restaurantes'),
                    ('menu_qr',       'Menú QR'),
                    ('menu_qr_visual','Menú QR Visual'),
                    ('menu_qr_marca', 'Menú QR Marca'),
                ],
                help_text='Canonical service type. Populated from default_service via data migration 0016.',
            ),
        ),
        migrations.AddField(
            model_name='business',
            name='country',
            field=models.CharField(max_length=2, default='AR'),
        ),
        migrations.AddField(
            model_name='business',
            name='currency',
            field=models.CharField(max_length=3, default='ARS'),
        ),
        migrations.AddField(
            model_name='business',
            name='timezone',
            field=models.CharField(max_length=64, default='America/Argentina/Buenos_Aires'),
        ),
        migrations.AddField(
            model_name='business',
            name='trial_starts_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='business',
            name='trial_ends_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='business',
            name='activated_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='business',
            name='suspended_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
        # auto_now=True: existing rows receive migration timestamp. Acceptable.
        migrations.AddField(
            model_name='business',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        # ── Indexes ─────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name='business',
            index=models.Index(fields=['status'], name='business_status_idx'),
        ),
        migrations.AddIndex(
            model_name='business',
            index=models.Index(fields=['parent'], name='business_parent_idx'),
        ),
        # ── Sparse unique on slug (allows multiple NULLs; enforces non-null uniqueness) ─
        migrations.AddConstraint(
            model_name='business',
            constraint=models.UniqueConstraint(
                fields=['slug'],
                condition=models.Q(slug__isnull=False),
                name='uq_business_slug',
            ),
        ),
    ]
