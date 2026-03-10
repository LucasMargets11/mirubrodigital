"""
Migration 0013 — Backfill email_verified for pre-existing active users.

Wave 1 (0012) backfilled ALL users with email_verified=False and
account_status='pending_email_verification'.  That is correct for brand-new
registrations, but breaks pre-existing users who were already active before
the email-verification gate was introduced.

This migration upgrades any AccountProfile whose owner:
  - Has an active Membership record (they are already operating users), OR
  - Is a Django staff/superuser (internal accounts).

These users are treated as implicitly verified and transitioned to
account_status='active'.

Rollback: Restores them to pending_email_verification / False.
  (This is safe — re-rolling backwards only re-sets the flag; the accounts
   keep working because HasBusinessMembership only blocks 'suspended' status
   in the initial enforcement gate — see B.1.b wave-2 note.)
"""

from django.db import migrations


def backfill_active_users(apps, schema_editor):
    """
    Grant email_verified=True to users who already have at least one Membership
    (they were actively using the platform before Wave 1) or are staff/superusers.
    """
    AccountProfile = apps.get_model('accounts', 'AccountProfile')
    Membership = apps.get_model('accounts', 'Membership')

    # Collect user IDs that should be implicitly verified.
    # 1. Users with any Membership (active platform users before migration).
    member_user_ids = set(
        Membership.objects.values_list('user_id', flat=True)
    )

    # 2. Staff / superusers.
    User = apps.get_model('auth', 'User')
    staff_user_ids = set(
        User.objects.filter(is_staff=True).values_list('pk', flat=True)
    )

    verified_user_ids = member_user_ids | staff_user_ids

    AccountProfile.objects.filter(
        user_id__in=verified_user_ids,
        email_verified=False,
    ).update(
        email_verified=True,
        account_status='active',
    )


def reverse_backfill(apps, schema_editor):
    """
    Roll back: demote re-verified users back to pending state.
    Intentionally conservative — does NOT clear email_verification_token_hash
    because those rows were None before this migration ran.
    """
    AccountProfile = apps.get_model('accounts', 'AccountProfile')
    Membership = apps.get_model('accounts', 'Membership')
    User = apps.get_model('auth', 'User')

    member_user_ids = set(Membership.objects.values_list('user_id', flat=True))
    staff_user_ids = set(User.objects.filter(is_staff=True).values_list('pk', flat=True))
    verified_user_ids = member_user_ids | staff_user_ids

    AccountProfile.objects.filter(
        user_id__in=verified_user_ids,
        email_verified=True,
        account_status='active',
    ).update(
        email_verified=False,
        account_status='pending_email_verification',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_accountprofile'),
    ]

    operations = [
        migrations.RunPython(
            backfill_active_users,
            reverse_backfill,
        ),
    ]
