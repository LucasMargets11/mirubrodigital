from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Slice 5A — state-only move of MercadoPagoConnection from apps.menu into
    this new generic app.

    This is a Django "move a model between apps" migration: it only updates
    migration STATE (so Django's ORM/model registry knows the model now lives
    in `merchant_payments`), it never touches the database. The model's
    `Meta.db_table` explicitly points at the original `menu_mercadopagoconnection`
    table, so no table rename, no data copy, and no risk to existing rows —
    every connection created before this slice is preserved untouched, same
    primary keys, same FK to Business.

    Paired with menu's `0014_remove_mercadopagoconnection_state_only.py`,
    which removes the model from menu's state (also without touching the DB).
    """

    dependencies = [
        ('business', '0001_initial'),
        ('menu', '0013_menucategory_product_category'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='MercadoPagoConnection',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('access_token', models.CharField(max_length=512)),
                        ('refresh_token', models.CharField(blank=True, max_length=512)),
                        ('token_expires_at', models.DateTimeField(blank=True, null=True)),
                        ('mp_user_id', models.CharField(blank=True, max_length=128)),
                        ('scope', models.CharField(blank=True, max_length=255)),
                        (
                            'status',
                            models.CharField(
                                choices=[
                                    ('connected', 'Connected'),
                                    ('expired', 'Expired'),
                                    ('revoked', 'Revoked'),
                                    ('error', 'Error'),
                                ],
                                default='connected',
                                max_length=16,
                            ),
                        ),
                        ('last_error', models.TextField(blank=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        (
                            'business',
                            models.OneToOneField(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name='mp_connection',
                                to='business.business',
                            ),
                        ),
                    ],
                    options={
                        'db_table': 'menu_mercadopagoconnection',
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
