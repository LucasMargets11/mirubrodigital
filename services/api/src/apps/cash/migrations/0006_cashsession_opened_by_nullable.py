# Phase POS-1 — Make CashSession.opened_by nullable
#
# Rationale: POS employee flows create sessions without a Django auth.User.
# The new canonical field is opened_by_employee (EmployeeProfile FK, added in 0004).
# Admin flows (dashboard) still populate opened_by when the actor is a real User.
#
# Risk: LOW — changing NOT NULL → NULL never requires a data migration.
# Existing rows retain their current opened_by values untouched.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cash', '0005_phase2a_operatorsession'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='cashsession',
            name='opened_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='cash_sessions_opened',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
