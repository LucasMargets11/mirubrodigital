"""
Tests para el motor de disponibilidad (Slice 0 teórica + Slice 3B real).

Cubre el algoritmo (`apps.appointments.services.availability`) a nivel
unitario -- horarios/excepciones (`AvailabilityEngineTests`) y ocupación real
por `Appointment` (`AvailabilityEngineOccupancyTests`) -- y el endpoint
`/api/v1/appointments/availability/` a nivel API (params, validaciones,
permisos, aislamiento multi-tenant).
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, Subscription

from ..models import (
    Appointment,
    AppointmentException,
    AppointmentProfessional,
    AppointmentSchedule,
    AppointmentService,
)
from ..services.availability import (
    ProfessionalCannotPerformService,
    ProfessionalInactive,
    ProfessionalNotFound,
    ServiceInactive,
    ServiceNotFound,
    compute_availability,
)

User = get_user_model()

# 2026-09-21 is a Monday (weekday=0), used as the canonical test date
# throughout so schedules/exceptions line up predictably.
MONDAY = dt.date(2026, 9, 21)


def _create_business(name='Turnos Biz', slug='turnos-biz', timezone='America/Argentina/Buenos_Aires'):
    biz = Business.objects.create(name=name, default_service='appointments', slug=slug, timezone=timezone)
    Subscription.objects.create(business=biz, plan=BusinessPlan.APPOINTMENTS_BASE, service='appointments', status='active')
    return biz


def _auth_client(client, business, role='owner'):
    user = User.objects.create_user(username=f'u-{business.slug}', password='pass1234')
    Membership.objects.create(user=user, business=business, role=role)
    client.force_authenticate(user=user)
    return user


def _slot_strs(result):
    return [(s.start.isoformat(), s.end.isoformat()) for s in result.slots]


def _create_appointment(
    business,
    service,
    professional=None,
    start_at=None,
    end_at=None,
    status=Appointment.Status.CONFIRMED,
):
    return Appointment.objects.create(
        business=business,
        service=service,
        professional=professional,
        customer_name='Cliente Test',
        customer_phone='+54 9 11 5555-5555',
        start_at=start_at,
        end_at=end_at,
        status=status,
        service_name=service.name,
        service_duration_minutes=service.duration_minutes,
        service_price=service.price,
        deposit_type=service.deposit_type,
        deposit_value=service.deposit_value,
    )


class AvailabilityEngineTests(TestCase):
    """Unit tests directos sobre `compute_availability`."""

    def setUp(self):
        self.biz = _create_business()
        self.service = AppointmentService.objects.create(
            business=self.biz, name='Corte', duration_minutes=30, price=100,
        )

    # 1. Horario general simple ------------------------------------------------
    def test_general_schedule_simple(self):
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='09:00', end_time='10:00',
        )
        result = compute_availability(business=self.biz, service_id=str(self.service.id), target_date=MONDAY)
        starts = [s.start.strftime('%H:%M') for s in result.slots]
        self.assertEqual(starts, ['09:00', '09:15', '09:30'])

    # 2. Múltiples bloques en un día --------------------------------------------
    def test_multiple_blocks_same_day(self):
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='09:00', end_time='10:00',
        )
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='15:00', end_time='16:00',
        )
        result = compute_availability(business=self.biz, service_id=str(self.service.id), target_date=MONDAY)
        starts = [s.start.strftime('%H:%M') for s in result.slots]
        self.assertEqual(starts, ['09:00', '09:15', '09:30', '15:00', '15:15', '15:30'])

    # 3. Negocio cerrado (sin schedule ni excepción) -----------------------------
    def test_business_closed_no_schedule(self):
        result = compute_availability(business=self.biz, service_id=str(self.service.id), target_date=MONDAY)
        self.assertEqual(result.slots, [])

    # 4. Excepción general cerrada -----------------------------------------------
    def test_business_exception_closed_overrides_weekly_schedule(self):
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='09:00', end_time='13:00',
        )
        AppointmentException.objects.create(
            business=self.biz, professional=None, date=MONDAY, is_closed=True,
        )
        result = compute_availability(business=self.biz, service_id=str(self.service.id), target_date=MONDAY)
        self.assertEqual(result.slots, [])

    # 5. Excepción general con horario especial -----------------------------------
    def test_business_exception_special_hours_replaces_weekly_schedule(self):
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='09:00', end_time='18:00',
        )
        AppointmentException.objects.create(
            business=self.biz, professional=None, date=MONDAY, is_closed=False,
            start_time='10:00', end_time='11:00',
        )
        result = compute_availability(business=self.biz, service_id=str(self.service.id), target_date=MONDAY)
        starts = [s.start.strftime('%H:%M') for s in result.slots]
        self.assertEqual(starts, ['10:00', '10:15', '10:30'])

    # 6/7. Profesional con horario propio + intersección negocio/profesional -----
    def test_professional_own_schedule_intersected_with_business(self):
        professional = AppointmentProfessional.objects.create(business=self.biz, name='Lucas')
        professional.services.add(self.service)
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='09:00', end_time='12:00',
        )
        AppointmentSchedule.objects.create(
            business=self.biz, professional=professional, weekday=0,
            start_time='10:00', end_time='14:00',
        )
        result = compute_availability(
            business=self.biz, service_id=str(self.service.id), target_date=MONDAY,
            professional_id=str(professional.id),
        )
        starts = [s.start.strftime('%H:%M') for s in result.slots]
        # Intersección negocio (09-12) ∩ profesional (10-14) = 10-12
        self.assertEqual(starts, ['10:00', '10:15', '10:30', '10:45', '11:00', '11:15', '11:30'])

    # 8. Excepción profesional ----------------------------------------------------
    def test_professional_exception_overrides_professional_weekly_schedule(self):
        professional = AppointmentProfessional.objects.create(business=self.biz, name='Lucas')
        professional.services.add(self.service)
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='09:00', end_time='18:00',
        )
        AppointmentSchedule.objects.create(
            business=self.biz, professional=professional, weekday=0,
            start_time='09:00', end_time='12:00',
        )
        AppointmentException.objects.create(
            business=self.biz, professional=professional, date=MONDAY, is_closed=True,
        )
        result = compute_availability(
            business=self.biz, service_id=str(self.service.id), target_date=MONDAY,
            professional_id=str(professional.id),
        )
        self.assertEqual(result.slots, [])

    def test_professional_exception_cannot_exceed_business_hours(self):
        """Una excepción de profesional nunca abre horario fuera del negocio."""
        professional = AppointmentProfessional.objects.create(business=self.biz, name='Lucas')
        professional.services.add(self.service)
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='09:00', end_time='12:00',
        )
        AppointmentException.objects.create(
            business=self.biz, professional=professional, date=MONDAY, is_closed=False,
            start_time='08:00', end_time='20:00',
        )
        result = compute_availability(
            business=self.biz, service_id=str(self.service.id), target_date=MONDAY,
            professional_id=str(professional.id),
        )
        starts = [s.start.strftime('%H:%M') for s in result.slots]
        self.assertEqual(starts[0], '09:00')
        self.assertEqual(starts[-1], '11:30')

    # 9. Servicio que no entra completo -------------------------------------------
    def test_service_does_not_fit_block(self):
        long_service = AppointmentService.objects.create(
            business=self.biz, name='Coloración', duration_minutes=45, price=200,
        )
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='09:00', end_time='09:40',
        )
        result = compute_availability(business=self.biz, service_id=str(long_service.id), target_date=MONDAY)
        self.assertEqual(result.slots, [])

    # 10. Granularidad 15 minutos --------------------------------------------------
    def test_granularity_matches_expected_example(self):
        """Ejemplo del enunciado: negocio 09-12, profesional Lucas 10-12, servicio 30 min."""
        professional = AppointmentProfessional.objects.create(business=self.biz, name='Lucas')
        professional.services.add(self.service)
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='09:00', end_time='12:00',
        )
        AppointmentSchedule.objects.create(
            business=self.biz, professional=professional, weekday=0,
            start_time='10:00', end_time='12:00',
        )
        result = compute_availability(
            business=self.biz, service_id=str(self.service.id), target_date=MONDAY,
            professional_id=str(professional.id),
        )
        starts = [s.start.strftime('%H:%M') for s in result.slots]
        self.assertEqual(starts, ['10:00', '10:15', '10:30', '10:45', '11:00', '11:15', '11:30'])

    # 11. Profesional no habilitado para el servicio -------------------------------
    def test_professional_not_enabled_for_service(self):
        professional = AppointmentProfessional.objects.create(business=self.biz, name='Lucas')
        # No se agrega el servicio a professional.services
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='09:00', end_time='12:00',
        )
        with self.assertRaises(ProfessionalCannotPerformService):
            compute_availability(
                business=self.biz, service_id=str(self.service.id), target_date=MONDAY,
                professional_id=str(professional.id),
            )

    def test_professional_without_own_schedule_not_available(self):
        """Profesional sin horario propio ese día => no disponible, aunque el negocio esté abierto."""
        professional = AppointmentProfessional.objects.create(business=self.biz, name='Lucas')
        professional.services.add(self.service)
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='09:00', end_time='12:00',
        )
        # Profesional tiene horario para otro día (martes), no para lunes.
        AppointmentSchedule.objects.create(
            business=self.biz, professional=professional, weekday=1,
            start_time='09:00', end_time='12:00',
        )
        result = compute_availability(
            business=self.biz, service_id=str(self.service.id), target_date=MONDAY,
            professional_id=str(professional.id),
        )
        self.assertEqual(result.slots, [])

    def test_inactive_professional_rejected(self):
        professional = AppointmentProfessional.objects.create(business=self.biz, name='Lucas', is_active=False)
        professional.services.add(self.service)
        with self.assertRaises(ProfessionalInactive):
            compute_availability(
                business=self.biz, service_id=str(self.service.id), target_date=MONDAY,
                professional_id=str(professional.id),
            )

    def test_inactive_service_rejected(self):
        self.service.is_active = False
        self.service.save(update_fields=['is_active'])
        with self.assertRaises(ServiceInactive):
            compute_availability(business=self.biz, service_id=str(self.service.id), target_date=MONDAY)

    # 12. Aislamiento multi-tenant ---------------------------------------------------
    def test_service_from_other_business_rejected(self):
        other_biz = _create_business(name='Other Biz', slug='other-biz-avail')
        other_service = AppointmentService.objects.create(
            business=other_biz, name='Corte', duration_minutes=30, price=100,
        )
        with self.assertRaises(ServiceNotFound):
            compute_availability(business=self.biz, service_id=str(other_service.id), target_date=MONDAY)

    def test_professional_from_other_business_rejected(self):
        other_biz = _create_business(name='Other Biz', slug='other-biz-avail-2')
        other_professional = AppointmentProfessional.objects.create(business=other_biz, name='Bruno')
        with self.assertRaises(ProfessionalNotFound):
            compute_availability(
                business=self.biz, service_id=str(self.service.id), target_date=MONDAY,
                professional_id=str(other_professional.id),
            )

    # 13. Timezone / date boundaries -------------------------------------------------
    def test_slots_use_business_timezone(self):
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='09:00', end_time='09:30',
        )
        result = compute_availability(business=self.biz, service_id=str(self.service.id), target_date=MONDAY)
        self.assertEqual(len(result.slots), 1)
        slot = result.slots[0]
        self.assertEqual(slot.start.utcoffset(), dt.timedelta(hours=-3))
        self.assertEqual(slot.start.date(), MONDAY)
        self.assertEqual(slot.start.strftime('%H:%M'), '09:00')

    def test_slots_use_configured_business_timezone_not_hardcoded(self):
        """No hardcodear Buenos Aires: si el negocio tiene otro timezone, se respeta."""
        biz_ny = _create_business(name='NY Biz', slug='ny-biz-avail', timezone='America/New_York')
        service = AppointmentService.objects.create(
            business=biz_ny, name='Corte', duration_minutes=30, price=100,
        )
        AppointmentSchedule.objects.create(
            business=biz_ny, professional=None, weekday=0,
            start_time='09:00', end_time='09:30',
        )
        result = compute_availability(business=biz_ny, service_id=str(service.id), target_date=MONDAY)
        self.assertEqual(len(result.slots), 1)
        # Fecha en septiembre => EDT (UTC-4)
        self.assertEqual(result.slots[0].start.utcoffset(), dt.timedelta(hours=-4))


class AvailabilityEngineOccupancyTests(TestCase):
    """Disponibilidad REAL (Slice 3B): descuenta `Appointment` ocupantes.

    Negocio Lunes 09:00-12:00, servicio 30 min => slots teóricos:
    09:00, 09:15, 09:30, 09:45, 10:00, 10:15, 10:30.
    """

    def setUp(self):
        self.biz = _create_business()
        self.service = AppointmentService.objects.create(
            business=self.biz, name='Corte', duration_minutes=30, price=100,
        )
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='09:00', end_time='12:00',
        )

    def _starts(self, **kwargs):
        result = compute_availability(
            business=self.biz, service_id=str(self.service.id), target_date=MONDAY, **kwargs,
        )
        return [s.start.strftime('%H:%M') for s in result.slots]

    def _dt(self, time_str):
        return dt.datetime.combine(
            MONDAY, dt.time.fromisoformat(time_str), tzinfo=ZoneInfo('America/Argentina/Buenos_Aires'),
        )

    # 1. confirmed elimina slot ----------------------------------------------
    def test_confirmed_appointment_removes_overlapping_slot(self):
        _create_appointment(
            self.biz, self.service,
            start_at=self._dt('10:00'), end_at=self._dt('10:30'),
        )
        starts = self._starts()
        # El turno 10:00-10:30 solapa los slots 09:45 (09:45-10:15), 10:00 y
        # 10:15 (10:15-10:45): los tres deben desaparecer, no solo 10:00.
        self.assertEqual(starts, ['09:00', '09:15', '09:30', '10:30', '10:45', '11:00', '11:15', '11:30'])

    # 2. solapamiento parcial elimina slot ------------------------------------
    def test_partial_overlap_removes_slot(self):
        # Turno 10:10-10:40 se superpone parcialmente con los slots
        # 09:45-10:15, 10:00-10:30, 10:15-10:45 y 10:30-11:00: los cuatro
        # deben desaparecer (comparación de intervalos, no solo start_at).
        _create_appointment(
            self.biz, self.service,
            start_at=self._dt('10:10'), end_at=self._dt('10:40'),
        )
        starts = self._starts()
        self.assertEqual(starts, ['09:00', '09:15', '09:30', '10:45', '11:00', '11:15', '11:30'])

    # 3. cancelled no bloquea --------------------------------------------------
    def test_cancelled_appointment_does_not_block(self):
        _create_appointment(
            self.biz, self.service,
            start_at=self._dt('10:00'), end_at=self._dt('10:30'),
            status=Appointment.Status.CANCELLED,
        )
        self.assertIn('10:00', self._starts())

    # 4. completed no bloquea ---------------------------------------------------
    def test_completed_appointment_does_not_block(self):
        _create_appointment(
            self.biz, self.service,
            start_at=self._dt('10:00'), end_at=self._dt('10:30'),
            status=Appointment.Status.COMPLETED,
        )
        self.assertIn('10:00', self._starts())

    # 5. no_show no bloquea -------------------------------------------------------
    def test_no_show_appointment_does_not_block(self):
        _create_appointment(
            self.biz, self.service,
            start_at=self._dt('10:00'), end_at=self._dt('10:30'),
            status=Appointment.Status.NO_SHOW,
        )
        self.assertIn('10:00', self._starts())

    # 6. turno de otro profesional no bloquea -------------------------------------
    def test_other_professional_appointment_does_not_block(self):
        prof_a = AppointmentProfessional.objects.create(business=self.biz, name='Lucas')
        prof_b = AppointmentProfessional.objects.create(business=self.biz, name='Bruno')
        for prof in (prof_a, prof_b):
            prof.services.add(self.service)
            AppointmentSchedule.objects.create(
                business=self.biz, professional=prof, weekday=0,
                start_time='09:00', end_time='12:00',
            )
        _create_appointment(
            self.biz, self.service, professional=prof_b,
            start_at=self._dt('10:00'), end_at=self._dt('10:30'),
        )
        starts = self._starts(professional_id=str(prof_a.id))
        self.assertIn('10:00', starts)

    # 7. turno de otro Business no bloquea -----------------------------------------
    def test_other_business_appointment_does_not_block(self):
        other_biz = _create_business(name='Other Biz', slug='other-biz-occupancy')
        other_service = AppointmentService.objects.create(
            business=other_biz, name='Corte', duration_minutes=30, price=100,
        )
        _create_appointment(
            other_biz, other_service,
            start_at=self._dt('10:00'), end_at=self._dt('10:30'),
        )
        self.assertIn('10:00', self._starts())

    # 8. appointment sin profesional bloquea disponibilidad general -----------------
    def test_appointment_without_professional_blocks_general_availability(self):
        _create_appointment(
            self.biz, self.service, professional=None,
            start_at=self._dt('10:00'), end_at=self._dt('10:30'),
        )
        self.assertNotIn('10:00', self._starts())

    # 9. appointment con profesional no bloquea la agenda del negocio (servicio sin profesionales)
    def test_appointment_with_professional_does_not_block_general_availability(self):
        # Slice 7B.1: `self.service` pasa a ser "con profesionales"; la agenda
        # del negocio se consulta con un servicio que no tiene ninguno.
        professional = AppointmentProfessional.objects.create(business=self.biz, name='Lucas')
        professional.services.add(self.service)
        AppointmentSchedule.objects.create(
            business=self.biz, professional=professional, weekday=0,
            start_time='09:00', end_time='12:00',
        )
        general_service = AppointmentService.objects.create(
            business=self.biz, name='Consulta', duration_minutes=30, price=100,
        )
        _create_appointment(
            self.biz, self.service, professional=professional,
            start_at=self._dt('10:00'), end_at=self._dt('10:30'),
        )
        # Disponibilidad general (servicio sin profesionales) no se ve afectada.
        general = compute_availability(business=self.biz, service_id=str(general_service.id), target_date=MONDAY)
        self.assertIn('10:00', [s.start.strftime('%H:%M') for s in general.slots])
        # Pero sí bloquea la disponibilidad de ESE profesional.
        self.assertNotIn('10:00', self._starts(professional_id=str(professional.id)))

    # 10. múltiples appointments -----------------------------------------------------
    def test_multiple_appointments_remove_multiple_slots(self):
        _create_appointment(
            self.biz, self.service,
            start_at=self._dt('09:00'), end_at=self._dt('09:30'),
        )
        _create_appointment(
            self.biz, self.service,
            start_at=self._dt('11:00'), end_at=self._dt('11:30'),
        )
        starts = self._starts()
        self.assertEqual(starts, ['09:30', '09:45', '10:00', '10:15', '10:30', '11:30'])

    # 11. exclude_appointment_id permite reprogramación ------------------------------
    def test_exclude_appointment_id_allows_rescheduling_itself(self):
        appointment = _create_appointment(
            self.biz, self.service,
            start_at=self._dt('10:00'), end_at=self._dt('10:30'),
        )
        self.assertNotIn('10:00', self._starts())
        starts_excluding_self = self._starts(exclude_appointment_id=str(appointment.id))
        self.assertIn('10:00', starts_excluding_self)

    # 12. timezone sigue correcto -----------------------------------------------------
    def test_occupancy_respects_business_timezone(self):
        biz_ny = _create_business(name='NY Biz', slug='ny-biz-occupancy', timezone='America/New_York')
        service = AppointmentService.objects.create(
            business=biz_ny, name='Corte', duration_minutes=30, price=100,
        )
        AppointmentSchedule.objects.create(
            business=biz_ny, professional=None, weekday=0,
            start_time='09:00', end_time='10:00',
        )
        # 10:00 UTC == 06:00 EDT (UTC-4 en septiembre), fuera del horario => no bloquea.
        _create_appointment(
            biz_ny, service,
            start_at=dt.datetime.combine(MONDAY, dt.time(10, 0), tzinfo=dt.timezone.utc),
            end_at=dt.datetime.combine(MONDAY, dt.time(10, 30), tzinfo=dt.timezone.utc),
        )
        result = compute_availability(business=biz_ny, service_id=str(service.id), target_date=MONDAY)
        starts = [s.start.strftime('%H:%M') for s in result.slots]
        self.assertIn('09:00', starts)

        # 13:30 UTC == 09:30 EDT, dentro del horario => bloquea ese slot.
        _create_appointment(
            biz_ny, service,
            start_at=dt.datetime.combine(MONDAY, dt.time(13, 30), tzinfo=dt.timezone.utc),
            end_at=dt.datetime.combine(MONDAY, dt.time(14, 0), tzinfo=dt.timezone.utc),
        )
        result = compute_availability(business=biz_ny, service_id=str(service.id), target_date=MONDAY)
        starts = [s.start.strftime('%H:%M') for s in result.slots]
        self.assertNotIn('09:30', starts)
        self.assertIn('09:00', starts)


class AvailabilityAPITests(APITestCase):
    """Tests de integración sobre el endpoint temporal `/availability/`."""

    def setUp(self):
        self.biz = _create_business()
        self.owner = _auth_client(self.client, self.biz, role='owner')
        self.service = AppointmentService.objects.create(
            business=self.biz, name='Corte', duration_minutes=30, price=100,
        )
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='09:00', end_time='10:00',
        )

    def _get(self, **params):
        return self.client.get('/api/v1/appointments/availability/', params)

    def test_returns_slots_for_valid_request(self):
        resp = self._get(service=str(self.service.id), date=MONDAY.isoformat())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['service'], str(self.service.id))
        self.assertIsNone(resp.data['professional'])
        self.assertEqual(len(resp.data['slots']), 3)
        self.assertEqual(resp.data['slots'][0]['start'][:16], f'{MONDAY.isoformat()}T09:00')

    def test_missing_service_param_rejected(self):
        resp = self._get(date=MONDAY.isoformat())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('service', resp.data)

    def test_missing_date_param_rejected(self):
        resp = self._get(service=str(self.service.id))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('date', resp.data)

    def test_invalid_date_format_rejected(self):
        resp = self._get(service=str(self.service.id), date='21-09-2026')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('date', resp.data)

    def test_closed_date_returns_empty_slots_not_error(self):
        # Domingo: no hay AppointmentSchedule configurado.
        sunday = dt.date(2026, 9, 20)
        resp = self._get(service=str(self.service.id), date=sunday.isoformat())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['slots'], [])

    def test_service_from_other_business_returns_400(self):
        other_biz = _create_business(name='Other Biz', slug='other-biz-avail-api')
        other_service = AppointmentService.objects.create(
            business=other_biz, name='Corte', duration_minutes=30, price=100,
        )
        resp = self._get(service=str(other_service.id), date=MONDAY.isoformat())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('service', resp.data)

    def test_professional_from_other_business_returns_400(self):
        other_biz = _create_business(name='Other Biz', slug='other-biz-avail-api-2')
        other_professional = AppointmentProfessional.objects.create(business=other_biz, name='Bruno')
        resp = self._get(
            service=str(self.service.id), date=MONDAY.isoformat(),
            professional=str(other_professional.id),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)

    def test_viewer_role_can_read_availability(self):
        viewer_biz = _create_business(name='Viewer Biz', slug='viewer-biz-avail')
        _auth_client(self.client, viewer_biz, role='viewer')
        service = AppointmentService.objects.create(
            business=viewer_biz, name='Corte', duration_minutes=30, price=100,
        )
        resp = self.client.get(
            '/api/v1/appointments/availability/',
            {'service': str(service.id), 'date': MONDAY.isoformat()},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_unauthenticated_rejected(self):
        self.client.force_authenticate(user=None)
        resp = self._get(service=str(self.service.id), date=MONDAY.isoformat())
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
