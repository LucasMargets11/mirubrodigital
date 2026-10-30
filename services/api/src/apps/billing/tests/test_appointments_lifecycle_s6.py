from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.appointments.models import (
    Appointment,
    AppointmentProfessional,
    AppointmentService,
)
from apps.appointments.services.professional_quota import (
    ProfessionalQuotaExceeded,
    ProfessionalQuotaUnavailable,
)
from apps.appointments.services.booking import BookingError, create_public_appointment
from apps.appointments.public_page import public_booking_unavailable_reason
from apps.appointments.serializers import AppointmentSerializer
from apps.billing.appointments_plans import EXTRA_PROFESSIONAL
from apps.billing.models import BillingInvoiceEvent, PendingSubscriptionChange, SubscriptionV2
from apps.billing.services.appointments_lifecycle import (
    GRACE_PERIOD,
    AppointmentsLifecycleError,
    apply_appointments_change,
    apply_appointments_renewal,
    appointments_v2_allows_creation,
    can_create_appointments,
    can_send_appointments_automation,
    can_start_ai_conversation,
    effective_usage_tier,
    prepare_appointments_provider_change,
    prorate_upgrade_amount,
    quote_appointments_change,
    record_appointments_payment_failure,
    resolve_professional_excess,
    request_appointments_change,
    subscription_lifecycle_access,
)
from apps.billing.tasks import _transition_past_due_to_suspended
from apps.business.models import Business, SubscriptionAddon
from apps.customers.models import Customer

User = get_user_model()


class AppointmentsProrationS6Tests(TestCase):
    def test_exact_monthly_and_annual_proration_uses_decimal_arithmetic(self):
        start = timezone.now()
        end = start + timedelta(days=30)
        halfway = start + timedelta(days=15)
        self.assertEqual(
            prorate_upgrade_amount(
                current_amount=23000,
                target_amount=28000,
                period_start=start,
                period_end=end,
                at=halfway,
            ),
            2500,
        )
        self.assertEqual(
            prorate_upgrade_amount(
                current_amount=Decimal('220800'),
                target_amount=Decimal('268800'),
                period_start=start,
                period_end=end,
                at=halfway,
            ),
            24000,
        )

    def test_proration_rounds_whole_peso_half_up_and_clamps_to_period(self):
        start = timezone.now()
        end = start + timedelta(days=3)
        self.assertEqual(
            prorate_upgrade_amount(
                current_amount=0,
                target_amount=1,
                period_start=start,
                period_end=end,
                at=start + timedelta(days=1, hours=12),
            ),
            1,
        )
        self.assertEqual(
            prorate_upgrade_amount(
                current_amount=0,
                target_amount=100,
                period_start=start,
                period_end=end,
                at=end,
            ),
            0,
        )
        with self.assertRaises(ValueError):
            prorate_upgrade_amount(
                current_amount=0,
                target_amount=100,
                period_start=end,
                period_end=start,
                at=start,
            )


class AppointmentsLifecycleS6Tests(TestCase):
    def setUp(self):
        self.now = timezone.now().replace(microsecond=0)
        self.period_start = self.now - timedelta(days=15)
        self.period_end = self.now + timedelta(days=15)
        self.user = User.objects.create_user(username=f'owner-{uuid.uuid4().hex[:8]}')
        self.business = Business.objects.create(
            name='Turnos lifecycle',
            default_service='appointments',
            slug=f'lifecycle-{uuid.uuid4().hex[:8]}',
            status='active',
        )
        self.subscription = self.make_subscription()
        self.service = AppointmentService.objects.create(
            business=self.business,
            name='Consulta',
            duration_minutes=30,
            price=Decimal('100'),
        )
        self.customer = Customer.objects.create(
            business=self.business,
            name='Cliente existente',
            phone='1122334455',
        )
        self.appointment = Appointment.objects.create(
            business=self.business,
            service=self.service,
            customer=self.customer,
            customer_name=self.customer.name,
            customer_phone=self.customer.phone,
            start_at=self.now + timedelta(days=3),
            end_at=self.now + timedelta(days=3, minutes=30),
            service_name=self.service.name,
            service_duration_minutes=30,
            service_price=self.service.price,
            deposit_type=self.service.deposit_type,
            deposit_value=self.service.deposit_value,
        )

    def make_subscription(self, plan='appointments', usage_tier=None, cycle='monthly', **values):
        defaults = {
            'business': self.business,
            'service_type': SubscriptionV2.ServiceType.APPOINTMENTS,
            'plan_code': plan,
            'usage_tier': usage_tier,
            'billing_cycle': cycle,
            'provider': SubscriptionV2.Provider.MANUAL,
            'external_reference': f'SUB-{uuid.uuid4()}',
            'status': SubscriptionV2.Status.ACTIVE,
            'is_active': True,
            'current_period_start': self.period_start,
            'current_period_end': self.period_end,
            'price_snapshot': {'total_amount': 23000, 'currency': 'ARS'},
        }
        defaults.update(values)
        return SubscriptionV2.objects.create(**defaults)

    def make_event(self, payment_id=None, *, paid_at=None):
        return BillingInvoiceEvent.objects.create(
            provider_authorized_payment_id=payment_id or f'auth-{uuid.uuid4()}',
            provider_status='authorized',
            paid_at=paid_at or self.period_end,
            amount=Decimal('23000'),
            currency='ARS',
        )

    def addon(self, code, quantity, *, active=True):
        return SubscriptionAddon.objects.create(
            subscription_v2=self.subscription,
            code=code,
            quantity=quantity,
            is_active=active,
        )

    def test_base_to_pro_upgrade_is_prorated_and_preserves_subscription_data(self):
        professional = AppointmentProfessional.objects.create(
            business=self.business,
            name='Profesional base',
        )
        extra = self.addon(EXTRA_PROFESSIONAL, 1)
        pending, quote = request_appointments_change(
            business=self.business,
            user=self.user,
            target={'plan_code': 'appointments_pro'},
            at=self.now,
        )
        self.assertEqual(pending.status, 'pending_payment')
        self.assertEqual(pending.total_amount, 2500)
        self.assertEqual(quote['proration']['amount_due_now'], 2500)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_code, 'appointments')
        self.assertEqual(self.subscription.current_period_end, self.period_end)

        self.assertTrue(apply_appointments_change(pending, payment_id='charge-pro', at=self.now))
        self.assertFalse(apply_appointments_change(pending, payment_id='charge-pro', at=self.now))
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_code, 'appointments_pro')
        self.assertEqual(self.subscription.current_period_end, self.period_end)
        self.assertTrue(AppointmentProfessional.objects.filter(pk=professional.pk).exists())
        self.assertTrue(Appointment.objects.filter(pk=self.appointment.pk).exists())
        extra.refresh_from_db()
        self.assertEqual(extra.quantity, 1)

    def test_pro_to_ai_and_ai_tier_upgrades_take_effect_immediately(self):
        self.subscription.plan_code = 'appointments_pro'
        self.subscription.save(update_fields=['plan_code'])
        pending, quote = request_appointments_change(
            business=self.business,
            user=self.user,
            target={'plan_code': 'appointments_ai', 'usage_tier': 'ai_300'},
            at=self.now,
        )
        self.assertEqual(pending.status, 'pending_payment')
        self.assertEqual(quote['amount_due_now'], 61000)
        apply_appointments_change(pending, payment_id='charge-ai', at=self.now)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_code, 'appointments_ai')
        self.assertEqual(self.subscription.usage_tier, 'ai_300')
        self.assertEqual(self.subscription.current_period_start, self.period_start)
        self.assertEqual(effective_usage_tier(self.subscription), {
            'effective_usage_tier': 'ai_300',
            'effective_from': self.now,
        })

        pending, quote = request_appointments_change(
            business=self.business,
            user=self.user,
            target={'usage_tier': 'ai_1500'},
            at=self.now,
        )
        self.assertEqual(quote['amount_due_now'], 62500)
        apply_appointments_change(pending, payment_id='charge-ai-1500', at=self.now)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.usage_tier, 'ai_1500')
        self.assertEqual(self.subscription.current_period_start, self.period_start)

    def test_downgrade_with_professional_excess_is_blocked_without_deleting_data(self):
        self.subscription.plan_code = 'appointments_pro'
        self.subscription.save(update_fields=['plan_code'])
        professionals = [
            AppointmentProfessional.objects.create(
                business=self.business,
                name=f'Pro {index}',
            )
            for index in range(3)
        ]
        pending, quote = request_appointments_change(
            business=self.business,
            user=self.user,
            target={'plan_code': 'appointments'},
            at=self.now,
        )
        self.assertEqual(pending.status, 'blocked')
        self.assertTrue(pending.requires_resolution)
        self.assertEqual(quote['resolution_details'] if 'resolution_details' in quote else pending.resolution_details, {
            'current_active_count': 3,
            'future_limit': 2,
            'excess_count': 1,
        })
        self.assertEqual(AppointmentProfessional.objects.filter(is_active=True).count(), 3)
        self.assertTrue(Appointment.objects.filter(pk=self.appointment.pk).exists())
        with self.assertRaises(AppointmentsLifecycleError):
            apply_appointments_change(pending, at=self.now)
        self.assertTrue(all(AppointmentProfessional.objects.filter(pk=item.pk).exists() for item in professionals))

    def test_downgrade_applies_on_renewal_only_after_professional_resolution(self):
        self.subscription.plan_code = 'appointments_pro'
        self.subscription.save(update_fields=['plan_code'])
        professionals = [
            AppointmentProfessional.objects.create(
                business=self.business,
                name=f'Team {index}',
            )
            for index in range(3)
        ]
        pending, _ = request_appointments_change(
            business=self.business,
            user=self.user,
            target={'plan_code': 'appointments'},
            at=self.now,
        )
        self.assertEqual(pending.status, 'blocked')
        professionals[0].is_active = False
        professionals[0].save(update_fields=['is_active'])
        pending = resolve_professional_excess(pending, at=self.now)
        self.assertEqual(pending.status, 'scheduled')
        event = self.make_event()
        self.assertTrue(apply_appointments_renewal(subscription=self.subscription, invoice_event=event))
        self.subscription.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(self.subscription.plan_code, 'appointments')
        self.assertEqual(pending.status, 'completed')
        self.assertEqual(self.subscription.current_period_start, self.period_end)
        self.assertTrue(Appointment.objects.filter(pk=self.appointment.pk).exists())
        self.assertFalse(apply_appointments_renewal(subscription=self.subscription, invoice_event=event))

    def test_scheduled_professional_downgrade_prevents_new_excess_activation(self):
        self.subscription.plan_code = 'appointments_pro'
        self.subscription.save(update_fields=['plan_code'])
        AppointmentProfessional.objects.create(business=self.business, name='Ana')
        AppointmentProfessional.objects.create(business=self.business, name='Beto')
        pending, _ = request_appointments_change(
            business=self.business,
            user=self.user,
            target={'plan_code': 'appointments'},
            at=self.now,
        )
        self.assertEqual(pending.status, 'scheduled')
        with self.assertRaises(ProfessionalQuotaExceeded):
            AppointmentProfessional.objects.create(business=self.business, name='Carla')

    def test_ai_tier_downgrade_is_scheduled_for_the_next_usage_period(self):
        self.subscription.plan_code = 'appointments_ai'
        self.subscription.usage_tier = 'ai_1500'
        self.subscription.price_snapshot = {'total_amount': 275000}
        self.subscription.save(update_fields=['plan_code', 'usage_tier', 'price_snapshot'])
        pending, _ = request_appointments_change(
            business=self.business,
            user=self.user,
            target={'usage_tier': 'ai_300'},
            at=self.now,
        )
        self.assertEqual(pending.status, 'scheduled')
        self.assertEqual(pending.scheduled_for, self.period_end)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.usage_tier, 'ai_1500')
        event = self.make_event()
        apply_appointments_renewal(subscription=self.subscription, invoice_event=event)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.usage_tier, 'ai_300')

    def test_billing_cycle_changes_are_explicit_quotes_effective_at_period_end(self):
        quote = quote_appointments_change(
            subscription=self.subscription,
            target={'billing_cycle': 'yearly'},
            at=self.now,
        )
        self.assertEqual(quote['current_billing_cycle'], 'monthly')
        self.assertEqual(quote['target']['billing_cycle'], 'yearly')
        self.assertEqual(quote['amount_due_now'], 0)
        self.assertEqual(quote['effective_at'], self.period_end)
        self.assertIsNotNone(quote['next_renewal_at'])

        annual = quote_appointments_change(
            subscription=self.subscription,
            target={'billing_cycle': 'yearly'},
            at=self.now,
        )
        self.assertEqual(annual['effective_at'], self.period_end)

    def test_annual_to_monthly_quote_does_not_shorten_paid_annual_period(self):
        self.subscription.billing_cycle = 'yearly'
        self.subscription.current_period_start = self.now - timedelta(days=200)
        self.subscription.current_period_end = self.now + timedelta(days=165)
        self.subscription.save(update_fields=[
            'billing_cycle', 'current_period_start', 'current_period_end',
        ])
        quote = quote_appointments_change(
            subscription=self.subscription,
            target={'billing_cycle': 'monthly'},
            at=self.now,
        )
        self.assertEqual(quote['effective_at'], self.period_end + timedelta(days=150))
        pending, _ = request_appointments_change(
            business=self.business,
            user=self.user,
            target={'billing_cycle': 'monthly'},
            at=self.now,
        )
        self.assertEqual(pending.scheduled_for, self.period_end + timedelta(days=150))
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.billing_cycle, 'yearly')

    def test_cycle_change_is_pending_until_renewal_and_preserves_extra_quantity(self):
        addon = self.addon(EXTRA_PROFESSIONAL, 2)
        pending, _ = request_appointments_change(
            business=self.business,
            user=self.user,
            target={'billing_cycle': 'yearly'},
            at=self.now,
        )
        self.assertEqual(pending.status, 'scheduled')
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.billing_cycle, 'monthly')
        event = self.make_event()
        apply_appointments_renewal(subscription=self.subscription, invoice_event=event)
        self.subscription.refresh_from_db()
        addon.refresh_from_db()
        self.assertEqual(self.subscription.billing_cycle, 'yearly')
        self.assertEqual(addon.quantity, 2)
        self.assertTrue(Appointment.objects.filter(pk=self.appointment.pk).exists())

    def test_provider_schedule_keeps_start_date_at_paid_period_end(self):
        self.subscription.provider = SubscriptionV2.Provider.MERCADOPAGO
        self.subscription.provider_sub_id = f'mp-{uuid.uuid4()}'
        self.subscription.save(update_fields=['provider', 'provider_sub_id'])
        pending, _ = request_appointments_change(
            business=self.business,
            user=self.user,
            target={'billing_cycle': 'yearly'},
            at=self.now,
        )
        with patch(
            'apps.billing.mp_service.MercadoPagoService.update_preapproval',
            return_value={'id': self.subscription.provider_sub_id},
        ) as update:
            self.assertTrue(prepare_appointments_provider_change(pending))
        payload = update.call_args.args[1]['auto_recurring']
        self.assertEqual(payload['transaction_amount'], 220800)
        self.assertEqual(payload['frequency'], 12)
        self.assertEqual(payload['start_date'], self.period_end.isoformat())
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.current_period_end, self.period_end)

    def test_renewal_is_idempotent_and_advances_one_period(self):
        event = self.make_event(payment_id='renewal-1')
        self.assertTrue(apply_appointments_renewal(
            subscription=self.subscription,
            invoice_event=event,
        ))
        self.subscription.refresh_from_db()
        first_end = self.subscription.current_period_end
        self.assertEqual(self.subscription.current_period_start, self.period_end)
        self.assertFalse(apply_appointments_renewal(
            subscription=self.subscription,
            invoice_event=event,
        ))
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.current_period_end, first_end)

    def test_failure_starts_exact_three_day_grace_and_suspension_preserves_appointments(self):
        self.assertTrue(record_appointments_payment_failure(
            subscription=self.subscription,
            at=self.now,
        ))
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, SubscriptionV2.Status.PAST_DUE)
        self.assertEqual(self.subscription.grace_started_at, self.now)
        self.assertEqual(self.subscription.grace_until, self.now + GRACE_PERIOD)
        self.assertTrue(can_create_appointments(self.business, at=self.now + timedelta(days=2)))
        self.assertFalse(can_create_appointments(self.business, at=self.now + timedelta(days=4)))
        with (
            patch('apps.billing.email_helpers.send_subscription_suspended_email'),
            patch('apps.accounts.admin_notification_service.create_admin_notification'),
        ):
            self.assertEqual(_transition_past_due_to_suspended(
                SubscriptionV2,
                self.now + timedelta(days=4),
            ), 1)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, SubscriptionV2.Status.SUSPENDED)
        self.assertIsNotNone(self.subscription.suspended_at)
        self.assertFalse(can_create_appointments(self.business, at=self.now + timedelta(days=4)))
        self.assertFalse(appointments_v2_allows_creation(self.business, at=self.now + timedelta(days=4)))
        self.assertTrue(Appointment.objects.filter(pk=self.appointment.pk).exists())

    def test_suspended_professional_activation_is_blocked_even_when_quota_remains(self):
        professional = AppointmentProfessional.objects.create(
            business=self.business,
            name='Inactive pro',
            is_active=False,
        )
        self.subscription.status = SubscriptionV2.Status.SUSPENDED
        self.subscription.save(update_fields=['status'])
        professional.is_active = True
        with self.assertRaises(ProfessionalQuotaUnavailable):
            professional.save(update_fields=['is_active'])

    def test_paid_reactivation_restores_access_without_regenerating_history(self):
        self.subscription.status = SubscriptionV2.Status.SUSPENDED
        self.subscription.grace_started_at = self.now - GRACE_PERIOD
        self.subscription.grace_until = self.now
        self.subscription.save(update_fields=['status', 'grace_started_at', 'grace_until'])
        event = self.make_event(payment_id='reactivation')
        self.assertTrue(apply_appointments_renewal(subscription=self.subscription, invoice_event=event))
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, SubscriptionV2.Status.ACTIVE)
        self.assertIsNone(self.subscription.grace_started_at)
        self.assertTrue(can_create_appointments(self.business))
        self.assertEqual(Appointment.objects.filter(pk=self.appointment.pk).count(), 1)

    def test_cancellation_keeps_access_until_period_end(self):
        from apps.billing.cancellation_service import schedule_cancellation

        with (
            patch('apps.billing.email_helpers.send_admin_cancellation_request_received_email'),
            patch('apps.accounts.admin_notification_service.create_admin_notification'),
        ):
            schedule_cancellation(self.subscription)
        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.cancel_at_period_end)
        self.assertTrue(subscription_lifecycle_access(self.subscription, at=self.now))
        self.assertFalse(subscription_lifecycle_access(self.subscription, at=self.period_end))
        self.assertTrue(Appointment.objects.filter(pk=self.appointment.pk).exists())

    def test_public_and_admin_creation_paths_block_suspended_subscription(self):
        self.subscription.status = SubscriptionV2.Status.SUSPENDED
        self.subscription.save(update_fields=['status'])
        self.assertIsNotNone(public_booking_unavailable_reason(self.business))
        with self.assertRaises(BookingError):
            create_public_appointment(
                business=self.business,
                service_id=str(self.service.pk),
                professional_id=None,
                start_at=self.now + timedelta(days=4),
                customer_name='Nueva reserva',
                customer_phone='1199999999',
            )
        serializer = AppointmentSerializer()
        with self.assertRaises(DRFValidationError):
            serializer.create({
                'business': self.business,
                'service': self.service,
                'professional': None,
                'start_at': self.now + timedelta(days=4),
                'customer_name': 'Nuevo turno',
                'customer_phone': '1188888888',
            })
        self.assertTrue(Appointment.objects.filter(pk=self.appointment.pk).exists())

    def test_cancel_effective_transition_keeps_existing_appointments(self):
        from apps.billing.cancellation_service import execute_cancellation, schedule_cancellation

        with (
            patch('apps.billing.email_helpers.send_admin_cancellation_request_received_email'),
            patch('apps.accounts.admin_notification_service.create_admin_notification'),
        ):
            schedule_cancellation(self.subscription)
        with patch('apps.billing.email_helpers.send_cancellation_confirmed_email'):
            execute_cancellation(self.subscription)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, SubscriptionV2.Status.CANCELED)
        self.assertFalse(can_create_appointments(self.business))
        self.assertTrue(Appointment.objects.filter(pk=self.appointment.pk).exists())

    def test_lifecycle_ai_policy_requires_active_ai_entitlement(self):
        self.assertFalse(can_start_ai_conversation(self.business, at=self.now))
        self.assertFalse(can_send_appointments_automation(self.business, at=self.now))
        self.subscription.plan_code = 'appointments_ai'
        self.subscription.usage_tier = 'ai_300'
        self.subscription.save(update_fields=['plan_code', 'usage_tier'])
        self.assertTrue(can_start_ai_conversation(self.business, at=self.now))
        self.assertTrue(can_send_appointments_automation(self.business, at=self.now))
        self.subscription.status = SubscriptionV2.Status.CANCELED
        self.subscription.save(update_fields=['status'])
        self.assertFalse(can_start_ai_conversation(self.business, at=self.now))
        self.assertFalse(can_send_appointments_automation(self.business, at=self.now))

    def test_legacy_appointments_base_and_other_service_are_not_migrated(self):
        self.subscription.status = SubscriptionV2.Status.CANCELED
        self.subscription.save(update_fields=['status'])
        legacy_business = Business.objects.create(
            name='Legacy appointments_base',
            default_service='appointments',
            slug=f'legacy-{uuid.uuid4().hex[:8]}',
            status='active',
        )
        self.assertIsNone(appointments_v2_allows_creation(legacy_business, at=self.now))
        self.subscription.service_type = SubscriptionV2.ServiceType.GESTION
        self.subscription.save(update_fields=['service_type'])
        self.assertFalse(subscription_lifecycle_access(self.subscription, at=self.now))

    def test_monthly_to_annual_quote_can_be_requested_without_mutation(self):
        pending, quote = request_appointments_change(
            business=self.business,
            user=self.user,
            target={'billing_cycle': 'yearly'},
            at=self.now,
        )
        self.assertEqual(pending.status, 'scheduled')
        self.assertEqual(quote['current_billing_cycle'], 'monthly')
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.billing_cycle, 'monthly')

    def test_upgrades_during_grace_are_rejected(self):
        record_appointments_payment_failure(subscription=self.subscription, at=self.now)
        with self.assertRaises(AppointmentsLifecycleError):
            request_appointments_change(
                business=self.business,
                user=self.user,
                target={'plan_code': 'appointments_pro'},
                at=self.now,
            )
