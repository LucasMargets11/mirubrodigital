"""S8I deployment guards; database checks are opt-in so migrate can run first."""
from django.conf import settings
from django.core import checks
from django.db import DatabaseError, connections
from django.db.migrations.recorder import MigrationRecorder

from apps.appointments.models import (
    AppointmentAIUsageAuthorization, AppointmentAIUsageCharge, AppointmentAIUsageSession,
)


def ai_usage_database_ready(alias='default'):
    connection = connections[alias]
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
        cursor.fetchone()
    if ('appointments', '0015_ai_usage_authorization') not in MigrationRecorder(connection).applied_migrations():
        return False
    # Read the mapped columns too: a migration record alone does not prove schema readiness.
    for model in (AppointmentAIUsageAuthorization, AppointmentAIUsageSession, AppointmentAIUsageCharge):
        list(model.objects.using(alias).values_list()[:1])
    return True


@checks.register(checks.Tags.security)
def check_ai_usage_config(app_configs=None, **kwargs):
    if not getattr(settings, 'AI_USAGE_METERING_ENABLED', False):
        return []
    if not getattr(settings, 'AGENT_INTEGRATION_ENABLED', False):
        return [checks.Error(
            'AI_USAGE_METERING_ENABLED=true requires AGENT_INTEGRATION_ENABLED=true.',
            hint='Disable metering until the HMAC integration is ready.',
            id='appointments.E001',
        )]
    return []


@checks.register(checks.Tags.database)
def check_ai_usage_database(app_configs=None, databases=None, **kwargs):
    if not getattr(settings, 'AI_USAGE_METERING_ENABLED', False):
        return []
    issues = []
    for alias in databases or []:
        try:
            ready = ai_usage_database_ready(alias)
        except DatabaseError:
            ready = False
        if not ready:
            issues.append(checks.Error(
                'AI usage database is not ready.',
                hint='Disable metering, apply appointments.0015 and verify database connectivity/schema.',
                id='appointments.E002',
            ))
    return issues
