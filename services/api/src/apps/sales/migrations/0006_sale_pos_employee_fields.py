"""
Migration: add created_by_employee and cancelled_by_employee FKs to Sale.

These nullable FKs support the new operative POS flow:
  - created_by_employee  → set by PosSaleCreateView when a sale is created via X-Employee-Token.
  - cancelled_by_employee → reserved for future POS cancellation endpoints.

The existing created_by / cancelled_by (auth.User) FKs are intentionally preserved
to avoid breaking admin/backoffice flows.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('sales', '0005_quotesequence_quote_quoteitem_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='created_by_employee',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='sales_created',
                to='accounts.employeeprofile',
            ),
        ),
        migrations.AddField(
            model_name='sale',
            name='cancelled_by_employee',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='sales_cancelled',
                to='accounts.employeeprofile',
            ),
        ),
    ]
