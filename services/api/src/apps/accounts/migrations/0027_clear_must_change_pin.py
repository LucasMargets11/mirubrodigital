"""
Data migration: clear must_change_pin for all EmployeeProfile rows.

Context: self-service PIN change has been disabled. Employees with the
legacy must_change_pin=True flag would be permanently blocked from accessing
POS capabilities with no way to clear the flag.  This migration resolves
the issue by setting must_change_pin=False for every existing row.

Going forward, employee creation and PIN reset always set must_change_pin=False.
"""
from django.db import migrations


def clear_must_change_pin(apps, schema_editor):
    EmployeeProfile = apps.get_model('accounts', 'EmployeeProfile')
    updated = EmployeeProfile.objects.filter(must_change_pin=True).update(must_change_pin=False)
    if updated:
        print(f'\n  Cleared must_change_pin for {updated} employee(s)')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0026_alter_accessauditlog_action_and_more'),
    ]

    operations = [
        migrations.RunPython(clear_must_change_pin, migrations.RunPython.noop),
    ]
