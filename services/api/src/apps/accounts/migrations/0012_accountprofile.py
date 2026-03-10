"""
Migration 0012 — AccountProfile

Adds the AccountProfile model (OneToOne extension of the stock User model).
Includes a data-migration step to backfill existing users so they all have a
profile row after the schema change (email_verified=False by default).

Rollback notes:
  - Safe to reverse: drop accounts_accountprofile.  No FK from other tables.
  - Existing auth flow is unchanged — all paths use get_or_create defensively.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_profiles(apps, schema_editor):
    """Create AccountProfile rows for every existing User that doesn't have one."""
    User = apps.get_model(settings.AUTH_USER_MODEL.split('.')[0], settings.AUTH_USER_MODEL.split('.')[1])
    AccountProfile = apps.get_model('accounts', 'AccountProfile')
    existing_user_ids = set(AccountProfile.objects.values_list('user_id', flat=True))
    profiles = [
        AccountProfile(
            user_id=user.pk,
            account_status='pending_email_verification',
            email_verified=False,
        )
        for user in User.objects.exclude(pk__in=existing_user_ids)
    ]
    AccountProfile.objects.bulk_create(profiles, ignore_conflicts=True)


def reverse_backfill(apps, schema_editor):
    # Nothing to do — the schema migration drop handles it.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_alter_accessauditlog_action_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AccountProfile',
            fields=[
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    primary_key=True,
                    related_name='account_profile',
                    serialize=False,
                    to=settings.AUTH_USER_MODEL,
                )),
                ('account_status', models.CharField(
                    choices=[
                        ('active', 'Activo'),
                        ('pending_email_verification', 'Pendiente de verificación'),
                        ('suspended', 'Suspendido'),
                    ],
                    default='pending_email_verification',
                    max_length=32,
                )),
                ('email_verified', models.BooleanField(default=False)),
                ('email_verification_token_hash', models.CharField(
                    blank=True, db_index=True, max_length=64, null=True,
                )),
                ('email_verification_token_created_at', models.DateTimeField(blank=True, null=True)),
                ('password_reset_token_hash', models.CharField(
                    blank=True, db_index=True, max_length=64, null=True,
                )),
                ('password_reset_token_created_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Account Profile',
                'verbose_name_plural': 'Account Profiles',
            },
        ),
        # Backfill existing users so they all have a profile row.
        migrations.RunPython(backfill_profiles, reverse_code=reverse_backfill),
    ]
