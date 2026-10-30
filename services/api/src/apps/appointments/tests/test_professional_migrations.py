import uuid

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ProfessionalMigrationTests(TransactionTestCase):
    # Include unmanaged legacy FK dependents in the isolated PostgreSQL flush.
    available_apps = settings.INSTALLED_APPS

    def test_s4_forward_preserves_legacy_and_enforces_membership_constraints(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [
            ('accounts', '0033_accessauditlog_admin_qr_reviews_config_updated'),
            ('appointments', '0008_appointment_customer'),
        ]
        executor.migrate(before)
        try:
            historical = executor.loader.project_state(before).apps
            business = historical.get_model('business', 'Business').objects.create(
                name='Historical professionals', default_service='appointments',
            )
            professional_model = historical.get_model('appointments', 'AppointmentProfessional')
            old_professionals = [
                professional_model.objects.create(business=business, name=f'Legacy {index}')
                for index in range(3)
            ]
            user_app, user_name = settings.AUTH_USER_MODEL.split('.')
            user = historical.get_model(user_app, user_name).objects.create(
                username=f'migration-{uuid.uuid4().hex}',
            )
            membership = historical.get_model('accounts', 'Membership').objects.create(
                business=business, user=user, role='owner',
            )

            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            migrated = executor.loader.project_state(latest).apps
            professionals = migrated.get_model('appointments', 'AppointmentProfessional')
            rows = professionals.objects.filter(pk__in=[row.pk for row in old_professionals])
            self.assertEqual(rows.count(), 3)
            self.assertEqual(rows.filter(is_active=True, membership__isnull=True).count(), 3)
            member_model = migrated.get_model('accounts', 'Membership')
            self.assertEqual(member_model.objects.get(pk=membership.pk).role, 'owner')
            self.assertIn('professional', dict(member_model._meta.get_field('role').choices))

            first = rows.first()
            professionals.objects.filter(pk=first.pk).update(membership_id=membership.pk)
            with self.assertRaises(IntegrityError), transaction.atomic():
                professionals.objects.create(
                    business_id=business.pk, name='Duplicate', membership_id=membership.pk,
                )
            inactive = professionals.objects.create(
                business_id=business.pk, name='Inactive linked',
                membership_id=membership.pk, is_active=False,
            )
            with self.assertRaises(IntegrityError), transaction.atomic():
                professionals.objects.filter(pk=inactive.pk).update(is_active=True)
            with self.assertRaises(IntegrityError), transaction.atomic():
                professionals.objects.create(
                    business_id=business.pk, name='Invalid FK', membership_id=999999999,
                )
                with connection.cursor() as cursor:
                    cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')

            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute(
                        'SELECT indexdef FROM pg_indexes WHERE indexname = %s',
                        ['unique_active_professional_membership_business'],
                    )
                    definition = cursor.fetchone()[0]
                self.assertIn('UNIQUE INDEX', definition)
                self.assertIn('WHERE', definition)
                self.assertIn('is_active', definition)
                self.assertIn('membership_id IS NOT NULL', definition)
        finally:
            MigrationExecutor(connection).migrate(latest)
