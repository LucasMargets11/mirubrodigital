"""PROD-09C1 — Control independiente de atención automática de Recepcionista IA.

`ReceptionistConfig.automatic_attention_enabled`: lo escribe solo Platform
Admin, exige configuración lista, se pausa al volver a borrador y la
autorización IA de Recepcionista lo exige antes de admitir interacciones.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, migrations, models, transaction
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase, override_settings

from apps.accounts.models import AccessAuditLog
from apps.appointments.models import (
    AppointmentAIUsageAuthorization, AppointmentAIUsageCharge, AppointmentAIUsageSession,
)
from apps.billing.tests.test_reception_ai_consumption_02e2a import AI_SETTINGS, _Base as _AIBase
from apps.billing.tests.test_reception_service_02b import _business, _superadmin
from apps.leads.models import Lead, ReceptionistConfig
from apps.leads.services import receptionist_config as service

from .test_agent_receptionist_config_03c import _Base as _AgentConfigBase
from .test_receiver_api import ReceiverTestBase
from .test_receptionist_config_03a import complete
from .test_receptionist_config_api_03b import TENANT, admin_url, member_client, reception_business, staff_client

FIELD = 'automatic_attention_enabled'


def audits(business):
    return list(
        AccessAuditLog.objects.filter(entity_type='receptionist_config', business=business).order_by('created_at', 'id')
    )


class _ConfigBase(TestCase):
    def setUp(self):
        self.business = reception_business()
        self.admin = staff_client()
        self.owner, self.owner_user = member_client(self.business)

    def ready(self, business=None, **extra):
        return ReceptionistConfig.objects.create(business=business or self.business, status='ready', **complete(), **extra)

    def config(self, business=None):
        return ReceptionistConfig.objects.get(business=business or self.business)

    def patch_admin(self, body, business=None):
        return self.admin.patch(admin_url(business or self.business), body, format='json')


class ModelTests(_ConfigBase):
    def test_default_is_disabled_on_every_create_path(self):
        self.assertFalse(ReceptionistConfig(business=self.business).automatic_attention_enabled)
        self.assertEqual(self.owner.post(TENANT, complete(status='ready'), format='json').status_code, 201)
        self.assertFalse(self.config().automatic_attention_enabled)
        other = reception_business()
        self.assertEqual(self.admin.post(admin_url(other), complete(status='ready'), format='json').status_code, 201)
        self.assertFalse(self.config(other).automatic_attention_enabled)

    def test_enabled_requires_ready_in_clean_and_database(self):
        with self.assertRaises(ValidationError):
            ReceptionistConfig.objects.create(business=self.business, **complete(), **{FIELD: True})
        config = ReceptionistConfig.objects.create(business=self.business, **complete())
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReceptionistConfig.objects.filter(pk=config.pk).update(**{FIELD: True})

    def test_flag_change_moves_the_version(self):
        config = self.ready()
        config.automatic_attention_enabled = True
        config.save()
        self.assertEqual(config.version, 2)
        config.save()
        self.assertEqual(config.version, 2)


class EnableAndPauseTests(_ConfigBase):
    def test_admin_enables_and_pauses_with_version_and_audit(self):
        self.ready()
        response = self.patch_admin({'expected_version': 1, FIELD: True})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()['config'][FIELD], response.json()['config']['version']), (True, 2))
        self.assertEqual(response.json()['config']['status'], 'ready')
        paused = self.patch_admin({'expected_version': 2, FIELD: False})
        self.assertEqual((paused.json()['config'][FIELD], paused.json()['config']['version']), (False, 3))
        enabled, pause = audits(self.business)
        self.assertEqual(enabled.details['automatic_attention'], 'enabled')
        self.assertEqual(enabled.details['changed_fields'], [FIELD])
        self.assertEqual(enabled.details[FIELD], True)
        self.assertEqual(pause.details['automatic_attention'], 'paused')
        self.assertEqual(enabled.actor.account_profile.is_platform_staff, True)

    def test_noop_writes_no_version_and_no_audit(self):
        self.ready()
        for value, version in ((False, 1), (True, 1), (True, 2)):
            response = self.patch_admin({'expected_version': version, FIELD: value})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.config().version, 2)
        self.assertEqual(len(audits(self.business)), 1)

    def test_strict_boolean(self):
        self.ready()
        for value in (1, 0, 'true', 'false', None, [], {}):
            with self.subTest(value=value):
                response = self.patch_admin({'expected_version': 1, FIELD: value})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['code'], 'validation_error')
                self.assertIn(FIELD, response.json()['fields'])
        self.assertEqual((self.config().automatic_attention_enabled, self.config().version), (False, 1))

    def test_stale_version_conflicts(self):
        self.ready()
        response = self.patch_admin({'expected_version': 7, FIELD: True})
        self.assertEqual((response.status_code, response.json()['code']), (409, 'version_conflict'))
        self.assertFalse(self.config().automatic_attention_enabled)

    def test_enable_is_rejected_unless_ready(self):
        ReceptionistConfig.objects.create(business=self.business, **complete())  # completa pero borrador
        response = self.patch_admin({'expected_version': 1, FIELD: True})
        self.assertEqual((response.status_code, response.json()['code']), (400, 'validation_error'))
        self.assertIn(FIELD, response.json()['fields'])
        incomplete = reception_business()
        ReceptionistConfig.objects.create(business=incomplete, assistant_name='Ana')
        self.assertEqual(self.patch_admin({'expected_version': 1, FIELD: True}, incomplete).status_code, 400)
        self.assertEqual(audits(self.business) + audits(incomplete), [])
        # Mismo PATCH que la deja lista y la habilita: explícito y permitido.
        both = self.patch_admin({'expected_version': 1, 'status': 'ready', FIELD: True})
        self.assertEqual(both.status_code, 200, both.content)
        self.assertEqual((self.config().status, self.config().automatic_attention_enabled), ('ready', True))

    def test_draft_pauses_atomically_and_ready_does_not_reenable(self):
        self.ready(**{FIELD: True})
        response = self.patch_admin({'expected_version': 1, 'status': 'draft'})
        self.assertEqual(response.status_code, 200, response.content)
        config = self.config()
        self.assertEqual((config.status, config.automatic_attention_enabled, config.version), ('draft', False, 2))
        (log,) = audits(self.business)
        self.assertEqual(log.details['automatic_attention'], 'paused_by_draft')
        self.assertEqual(log.details['changed_fields'], [FIELD, 'status'])
        back = self.patch_admin({'expected_version': 2, 'status': 'ready'})
        self.assertEqual(back.status_code, 200)
        self.assertEqual((self.config().status, self.config().automatic_attention_enabled), ('ready', False))

    def test_draft_and_enable_in_the_same_patch_is_rejected(self):
        self.ready(**{FIELD: True})
        response = self.patch_admin({'expected_version': 1, 'status': 'draft', FIELD: True})
        self.assertEqual(response.status_code, 400)
        self.assertEqual((self.config().status, self.config().automatic_attention_enabled), ('ready', True))

    def test_merchant_moving_to_draft_also_pauses(self):
        self.ready(**{FIELD: True})
        response = self.owner.patch(TENANT, {'expected_version': 1, 'status': 'draft'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(self.config().automatic_attention_enabled)
        self.assertEqual(audits(self.business)[0].details['source'], 'business')

    def test_pause_works_whatever_the_commercial_state(self):
        from apps.billing.models import SubscriptionV2
        for status in ('suspended', 'past_due', 'trialing'):
            with self.subTest(status=status):
                business = _business()
                from apps.billing.tests.test_reception_service_02b import _reception
                _reception(business, status=status)
                self.ready(business, **{FIELD: True})
                response = self.patch_admin({'expected_version': 1, FIELD: False}, business)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertFalse(self.config(business).automatic_attention_enabled)
                self.assertTrue(SubscriptionV2.objects.filter(business=business, status=status).exists())

    def test_audit_failure_rolls_back(self):
        self.ready()
        with patch('apps.leads.services.receptionist_config.record_platform_action', side_effect=RuntimeError('audit down')):
            with self.assertRaises(RuntimeError):
                service.update_receptionist_config(
                    self.business, {'expected_version': 1, FIELD: True},
                    actor=_superadmin(), source=service.SOURCE_PLATFORM_ADMIN,
                )
        config = self.config()
        self.assertEqual((config.automatic_attention_enabled, config.version), (False, 1))
        self.assertEqual(audits(self.business), [])

    def test_businesses_are_isolated(self):
        self.ready()
        other = reception_business()
        self.ready(other)
        self.patch_admin({'expected_version': 1, FIELD: True})
        self.assertTrue(self.config().automatic_attention_enabled)
        self.assertFalse(self.config(other).automatic_attention_enabled)
        self.assertEqual(self.config(other).version, 1)


class MerchantAccessTests(_ConfigBase):
    def test_merchant_reads_but_cannot_write(self):
        self.ready(**{FIELD: True})
        self.assertIs(self.owner.get(TENANT).json()['config'][FIELD], True)
        for value in (False, True):
            response = self.owner.patch(TENANT, {'expected_version': 1, FIELD: value}, format='json')
            self.assertEqual((response.status_code, response.json()['code']), (400, 'protected_fields'))
            self.assertEqual(response.json()['fields'], [FIELD])
        self.assertEqual((self.config().automatic_attention_enabled, self.config().version), (True, 1))

    def test_create_never_accepts_the_flag(self):
        for client, path, business in ((self.owner, TENANT, self.business), (self.admin, admin_url(self.business), self.business)):
            with self.subTest(path=path):
                response = client.post(path, {**complete(status='ready'), FIELD: True}, format='json')
                self.assertEqual((response.status_code, response.json()['code']), (400, 'protected_fields'))
                self.assertFalse(ReceptionistConfig.objects.filter(business=business).exists())

    def test_operations_can_and_other_staff_roles_cannot(self):
        self.ready()
        self.assertEqual(staff_client('operations').patch(
            admin_url(self.business), {'expected_version': 1, FIELD: True}, format='json').status_code, 200)
        for role in ('support_agent', 'content_admin'):
            with self.subTest(role=role):
                response = staff_client(role).patch(admin_url(self.business), {'expected_version': 2, FIELD: False}, format='json')
                self.assertEqual(response.status_code, 403)
        self.assertTrue(self.config().automatic_attention_enabled)


@override_settings(**AI_SETTINGS)
class AuthorizationGateTests(_AIBase, TestCase):
    def pause(self, biz):
        config = ReceptionistConfig.objects.get(business=biz)
        service.update_receptionist_config(
            biz, {'expected_version': config.version, FIELD: False}, actor=_superadmin(),
            source=service.SOURCE_PLATFORM_ADMIN,
        )

    def resume(self, biz):
        config = ReceptionistConfig.objects.get(business=biz)
        service.update_receptionist_config(
            biz, {'expected_version': config.version, FIELD: True}, actor=_superadmin(),
            source=service.SOURCE_PLATFORM_ADMIN,
        )

    def ledger(self, biz):
        return tuple(
            model.objects.filter(business=biz).count()
            for model in (AppointmentAIUsageSession, AppointmentAIUsageAuthorization, AppointmentAIUsageCharge)
        )

    def test_paused_is_rejected_explicitly_without_consumption(self):
        biz = _business()
        self.reception(biz)
        conversation, credential, _ = self.agent(biz)
        self.pause(biz)
        body = self.authorize(credential, conversation, self.at)
        self.assertEqual((body['allowed'], body['reason']), (False, 'automatic_attention_disabled'))
        self.assertEqual(self.ledger(biz), (0, 0, 0))

    def test_missing_config_is_rejected(self):
        biz = _business()
        self.reception(biz)
        conversation, credential, _ = self.agent(biz)
        ReceptionistConfig.objects.filter(business=biz).delete()
        body = self.authorize(credential, conversation, self.at)
        self.assertEqual((body['allowed'], body['reason']), (False, 'automatic_attention_disabled'))
        self.assertEqual(self.ledger(biz), (0, 0, 0))

    def test_replays_and_open_windows_do_not_bypass_a_pause_and_history_is_kept(self):
        biz = _business()
        self.reception(biz)
        conversation, credential, _ = self.agent(biz)
        first = uuid.uuid4()
        self.assertTrue(self.authorize(credential, conversation, self.at, interaction=first)['allowed'])
        before = self.ledger(biz)
        self.assertEqual(before, (1, 1, 1))
        self.pause(biz)
        replay = self.authorize(credential, conversation, self.at + timedelta(hours=1), interaction=first, occurred=self.at)
        same_window = self.authorize(credential, conversation, self.at + timedelta(hours=2))
        for body in (replay, same_window):
            self.assertEqual((body['allowed'], body['reason']), (False, 'automatic_attention_disabled'))
        self.assertEqual(self.ledger(biz), before)  # sesiones, recibos y cargos previos intactos
        self.resume(biz)
        again = self.authorize(credential, conversation, self.at + timedelta(hours=3), interaction=first, occurred=self.at)
        self.assertEqual((again['allowed'], again['created']), (True, False))
        self.assertEqual(self.ledger(biz), before)

    def test_other_businesses_keep_working(self):
        paused, active = _business(), _business()
        for biz in (paused, active):
            self.reception(biz)
        paused_conv, paused_cred, _ = self.agent(paused)
        active_conv, active_cred, _ = self.agent(active)
        self.pause(paused)
        self.assertFalse(self.authorize(paused_cred, paused_conv, self.at)['allowed'])
        self.assertTrue(self.authorize(active_cred, active_conv, self.at)['allowed'])

    def test_turnos_ia_is_not_gated(self):
        biz = _business(service='appointments')
        self.sub(biz, 'appointments', 'appointments_ai', 'ai_300')
        conversation, credential, _ = self.agent(biz)
        # Ni sin configuración ni con una configuración pausada se bloquea Turnos IA.
        ReceptionistConfig.objects.filter(business=biz).update(**{FIELD: False})
        self.assertTrue(self.authorize(credential, conversation, self.at)['allowed'])
        ReceptionistConfig.objects.filter(business=biz).delete()
        self.assertTrue(self.authorize(credential, conversation, self.at + timedelta(minutes=1))['allowed'])


class AgentContractTests(_AgentConfigBase):
    def test_ready_and_paused_keeps_real_status_and_reports_the_flag(self):
        ReceptionistConfig.objects.create(business=self.business, status='ready', **complete())
        body = self.ok(self.get())
        self.assertEqual((body['config']['status'], body['config'][FIELD]), ('ready', False))
        self.assertIsNotNone(body['config']['content'])  # no se simula borrador
        ReceptionistConfig.objects.filter(business=self.business).update(**{FIELD: True})
        self.assertIs(self.ok(self.get())['config'][FIELD], True)

    def test_draft_reports_disabled(self):
        ReceptionistConfig.objects.create(business=self.business, **complete())
        body = self.ok(self.get())
        self.assertEqual((body['config']['status'], body['config'][FIELD], body['config']['content']), ('draft', False, None))


class HumanAttentionTests(ReceiverTestBase):
    def test_lead_sync_and_handoff_are_unaffected_by_a_pause(self):
        ReceptionistConfig.objects.create(business=self.business, status='ready', **complete())  # pausada
        payload = self.payload(handoff={'requested': True, 'requested_at': '2026-10-04T12:05:00.000000Z', 'reasons': [
            {'code': 'patient_asked_human', 'first_at': '2026-10-04T12:05:00.000000Z', 'last_at': '2026-10-04T12:05:00.000000Z'},
        ]})
        response = self.put(payload)
        self.assertEqual(response.status_code, 201, response.content)
        lead = Lead.objects.get(business=self.business)
        self.assertTrue(lead.agent_state.handoff_requested)


class MigrationTests(TestCase):
    """0016 agrega el campo con default False (las filas existentes quedan en
    False) y la constraint; no hay pasos de datos que lo enciendan."""

    def test_migration_adds_a_disabled_field_without_data_steps(self):
        migration = MigrationLoader(connection).get_migration('leads', '0016_receptionist_config_automatic_attention')
        add_field, add_constraint = migration.operations
        self.assertIsInstance(add_field, migrations.AddField)
        self.assertEqual((add_field.model_name, add_field.name), ('receptionistconfig', FIELD))
        self.assertIsInstance(add_field.field, models.BooleanField)
        self.assertIs(add_field.field.default, False)
        self.assertIsInstance(add_constraint, migrations.AddConstraint)
        self.assertEqual(add_constraint.constraint.name, 'receptionist_config_attention_requires_ready')
        self.assertFalse(any(isinstance(op, (migrations.RunPython, migrations.RunSQL)) for op in migration.operations))
        self.assertEqual(migration.dependencies[-1], ('leads', '0015_whatsapp_authorization'))

    def test_applied_column_is_a_not_null_boolean(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT is_nullable, data_type FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = %s",
                [ReceptionistConfig._meta.db_table, FIELD],
            )
            self.assertEqual(cursor.fetchone(), ('NO', 'boolean'))
