"""
Migration 0008 – Fix checkout session constraints

Changes:
  1. MpCheckoutSession.idempotency_key:
       - Remove UNIQUE constraint (was blocking new sessions after expiry/completion
         for the same user+plan — the partial unique constraints are sufficient).
       - Retain a plain DB index (fast lookup during select_for_update).

  2. MpCheckoutSession partial unique constraints:
       - Drop old constraint: uq_checkout_session_open_per_user_plan
         (was (user, plan) without tenant — allowed cross-tenant collisions).
       - Add new constraint: uq_checkout_session_open_per_tenant_user_plan
         (user, tenant, plan) WHERE tenant IS NOT NULL AND status IN open.
       - Add new constraint: uq_checkout_session_open_per_user_plan_notenant
         (user, plan) WHERE tenant IS NULL AND status IN open.
         Covers the new-signup path before a tenant is assigned.

  3. MpCheckoutSession index:
       - Drop old: checkout_sess_user_plan_idx (user, plan, status)
       - Add new:  co_sess_user_tenant_plan_idx (user, tenant, plan, status)
         NOTE: shortened to 28 chars to satisfy Django's 30-char index name limit.
"""
from __future__ import annotations

from django.db import migrations, models
import django.db.models.expressions


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0007_phase3_checkout_session_webhook_delivery'),
    ]

    operations = [
        # ── 1. Remove UNIQUE from idempotency_key, keep a plain index ─────────
        migrations.AlterField(
            model_name='mpcheckoutsession',
            name='idempotency_key',
            field=models.CharField(
                max_length=128,
                db_index=True,
                help_text=(
                    'sha256(user_pk:tenant_pk:plan_code). Not unique at DB level — '
                    'deduplication of open sessions is enforced by the partial '
                    'unique constraints below. Not unique here allows new sessions '
                    'to be created for the same user+plan after a previous one expires.'
                ),
            ),
        ),

        # ── 2. Drop old single-level constraint ───────────────────────────────
        migrations.RemoveConstraint(
            model_name='mpcheckoutsession',
            name='uq_checkout_session_open_per_user_plan',
        ),

        # ── 3. Drop old index ──────────────────────────────────────────────────
        migrations.RemoveIndex(
            model_name='mpcheckoutsession',
            name='checkout_sess_user_plan_idx',
        ),

        # ── 4. Add: at most one open session per (user, tenant, plan) ─────────
        migrations.AddConstraint(
            model_name='mpcheckoutsession',
            constraint=models.UniqueConstraint(
                fields=['user', 'tenant', 'plan'],
                condition=django.db.models.expressions.Q(
                    status__in=['created', 'checkout_created', 'awaiting_webhook', 'linked'],
                    tenant__isnull=False,
                ),
                name='uq_checkout_session_open_per_tenant_user_plan',
            ),
        ),

        # ── 5. Add: at most one open session per (user, plan) — NULL tenant ───
        migrations.AddConstraint(
            model_name='mpcheckoutsession',
            constraint=models.UniqueConstraint(
                fields=['user', 'plan'],
                condition=django.db.models.expressions.Q(
                    status__in=['created', 'checkout_created', 'awaiting_webhook', 'linked'],
                    tenant__isnull=True,
                ),
                name='uq_checkout_session_open_per_user_plan_notenant',
            ),
        ),

        # ── 6. Add new composite index ────────────────────────────────────────
        migrations.AddIndex(
            model_name='mpcheckoutsession',
            index=models.Index(
                fields=['user', 'tenant', 'plan', 'status'],
                name='co_sess_user_tenant_plan_idx',
            ),
        ),
    ]
