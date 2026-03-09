# Make target_user nullable so employee-related audit entries can be created
# without a corresponding User object.  Employee actions use entity_type/entity_id
# (added in migration 0009) to reference the affected EmployeeProfile row.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_phase2a_accessauditlog_extend'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='accessauditlog',
            name='target_user',
            field=models.ForeignKey(
                blank=True,
                help_text='User affected by the action. NULL for employee-only actions.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='audit_actions_received',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
