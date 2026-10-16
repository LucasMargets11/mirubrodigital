"""
Seed local de QA manual para MiRubro Turnos (solo desarrollo).

Crea dos tenants, ambos con la configuración canónica de un piloto
(`SubscriptionV2` provider=MANUAL, plan_code=`appointments_base`, status
active) y respetando el límite real de asientos de `appointments_base`
(owner no consume asiento; 2 usuarios secundarios):

  QA Turnos (`qa-turnos`)                 owner + admin + manager
    3 categorías, 5 servicios (sin seña, seña fija, porcentaje),
    2 profesionales, horarios semanales, una excepción y turnos en distintos
    estados — incluidos un pago aprobado y uno `requires_review` aplicados
    con el servicio real `payment_confirmation.apply_provider_payment` sobre
    un payload SIMULADO (genera también las BusinessNotifications).

    Los turnos se vinculan a `customers.Customer` con el mismo resolver que
    producción (`services.customer_link`, un teléfono por persona) e incluyen
    historial pasado (completed / no_show / cancelled) para la ficha de
    Clientes (Turnos CUSTOMER 02).

  QA Turnos Viewer (`qa-turnos-viewer`)   owner-viewer + viewer
    Copia mínima (1 categoría, 1 servicio, horarios, algunos turnos) para
    probar permisos de VIEWER. Sin fixtures financieros.

Nunca se llama a Mercado Pago: no se crea `MercadoPagoConnection` ni
Preferences reales. No se usa billing legacy (`business.Subscription`) ni se
saltea ningún chequeo: las Membership pasan por el chequeo real de asientos
y, al final, se verifica el contexto de entitlement que usa la sesión.

Uso (dentro del contenedor/entorno de la API, con DJANGO_DEBUG=true):

    QA_TURNOS_PASSWORD='<elegida>' python manage.py seed_turnos_qa
    python manage.py seed_turnos_qa --password '<elegida>'
    python manage.py seed_turnos_qa            # genera una password aleatoria y la imprime
    python manage.py seed_turnos_qa --reset    # borra SOLO los datos de este seed

Cada ejecución sin `--reset` borra y recrea el seed (reproducible).

Alcance del borrado: los Business `qa-turnos` y `qa-turnos-viewer`
(verificando nombre y servicio) y los usuarios `*@qa-turnos.test`. Si algún
slug pertenece a otro negocio o algún usuario QA tiene membresías en un
Business ajeno al seed, el comando aborta sin borrar nada.
"""
from __future__ import annotations

import datetime as dt
import os
import secrets
import uuid
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone as dj_timezone

from apps.accounts.models import AccountProfile, Membership
from apps.appointments.models import (
  Appointment,
  AppointmentCategory,
  AppointmentException,
  AppointmentPayment,
  AppointmentProfessional,
  AppointmentSchedule,
  AppointmentService,
)
from apps.appointments.public_page import build_public_booking_url
from apps.appointments.services import payment_confirmation
from apps.appointments.services.customer_link import resolve_customer_for_appointment
from apps.billing.models import SubscriptionV2
from apps.business.context import build_business_context
from apps.business.models import Business

User = get_user_model()

BUSINESS_TZ = 'America/Argentina/Buenos_Aires'
PLAN_CODE = 'appointments_base'
EMAIL_DOMAIN = 'qa-turnos.test'
PASSWORD_ENV = 'QA_TURNOS_PASSWORD'
# Prefijo de ids simulados: nunca colisiona con ids numéricos reales de MP.
FAKE_ID_PREFIX = 'QA-SEED'

MAIN = {'name': 'QA Turnos', 'slug': 'qa-turnos', 'members': [('owner', 'owner'), ('admin', 'admin'), ('manager', 'manager')]}
VIEWER = {'name': 'QA Turnos Viewer', 'slug': 'qa-turnos-viewer', 'members': [('owner-viewer', 'owner'), ('viewer', 'viewer')]}
TENANTS = (MAIN, VIEWER)

FRONT = (getattr(settings, 'FRONTEND_URL', None) or 'http://localhost:3000').rstrip('/')


def qa_email(local: str) -> str:
  return f'{local}@{EMAIL_DOMAIN}'


class Command(BaseCommand):
  help = 'Seed local de QA manual para Turnos (solo DEBUG). --reset borra solo estos datos.'

  def add_arguments(self, parser):
    parser.add_argument('--reset', action='store_true', help='Borra los datos del seed QA y termina.')
    parser.add_argument(
      '--password',
      help=f'Password de los usuarios QA. Alternativa: variable de entorno {PASSWORD_ENV}. '
           'Si falta, se genera una aleatoria.',
    )
    parser.add_argument(
      '--hold-minutes', type=int, default=60,
      help='Vigencia del hold de los turnos pending_payment "vigentes" (default 60; en producción es 10).',
    )

  # ── Entrada ─────────────────────────────────────────────────────────────────

  def handle(self, *args, **opts):
    if not settings.DEBUG:
      raise CommandError('seed_turnos_qa solo corre con DEBUG=True (desarrollo local). Sin excepciones.')

    with transaction.atomic():
      self._reset()
      if opts['reset']:
        self.stdout.write(self.style.SUCCESS('Seed QA Turnos borrado.'))
        return

      password, generated = self._resolve_password(opts.get('password'))
      self.tz = ZoneInfo(BUSINESS_TZ)
      self.now = dj_timezone.now()
      self.hold_minutes = opts['hold_minutes']
      self.phones = {}

      main = self._create_tenant(MAIN, password)
      services, pros = self._create_catalog(main)
      days, closed_day = self._create_schedules(main, pros)
      main_appts = self._create_appointments(main, services, pros, days)

      viewer = self._create_tenant(VIEWER, password)
      viewer_appts = self._create_viewer_fixtures(viewer, days)

      for business in (main, viewer):
        self._verify_entitlement(business)

    self._print_summary(main, main_appts, viewer, viewer_appts, password, generated, closed_day)

  # ── Reset ───────────────────────────────────────────────────────────────────

  def _reset(self) -> None:
    businesses = []
    for tenant in TENANTS:
      business = Business.objects.filter(slug=tenant['slug']).first()
      if business is None:
        continue
      if business.name != tenant['name'] or business.default_service != 'appointments':
        raise CommandError(
          f'Existe un Business con slug "{tenant["slug"]}" que no es del seed '
          f'(name={business.name!r}, service={business.default_service!r}). No se toca nada.'
        )
      businesses.append(business)

    users = list(User.objects.filter(email__iendswith=f'@{EMAIL_DOMAIN}'))
    if Membership.objects.filter(user__in=users).exclude(business__in=businesses).exists():
      raise CommandError(
        f'Hay usuarios @{EMAIL_DOMAIN} con membresías en negocios ajenos al seed; no se borra nada.'
      )

    for business in businesses:
      # PROTECT: `Appointment.service` y `SubscriptionV2.business` se borran
      # explícitamente antes que el Business (pagos/notificaciones: CASCADE).
      Appointment.objects.filter(business=business).delete()
      SubscriptionV2.objects.filter(business=business).delete()
      business.delete()
      self.stdout.write(f'  borrado Business {business.slug}')
    for user in users:
      user.delete()
    if users:
      self.stdout.write(f'  borrados {len(users)} usuarios @{EMAIL_DOMAIN}')

  def _resolve_password(self, cli_password):
    password = cli_password or os.environ.get(PASSWORD_ENV, '')
    if password:
      return password, False
    return secrets.token_urlsafe(12), True

  # ── Tenant: Business + SubscriptionV2 + usuarios ────────────────────────────

  def _create_tenant(self, tenant, password) -> Business:
    business = Business.objects.create(
      name=tenant['name'], slug=tenant['slug'], default_service='appointments',
      service_type=Business.ServiceType.APPOINTMENTS, status='active', timezone=BUSINESS_TZ,
      activated_at=self.now,
    )
    # Misma forma que el aprovisionamiento manual de un piloto.
    SubscriptionV2.objects.create(
      business=business,
      service_type=SubscriptionV2.ServiceType.APPOINTMENTS,
      plan_code=PLAN_CODE,
      provider=SubscriptionV2.Provider.MANUAL,
      external_reference=f'SUB-{uuid.uuid4()}',
      status=SubscriptionV2.Status.ACTIVE,
      is_active=True,
      current_period_start=self.now,
      manual_grant_reason='Seed QA local (seed_turnos_qa)',
    )
    for local, role in tenant['members']:
      user = User.objects.create_user(
        username=f'qa_turnos_{local.replace("-", "_")}', email=qa_email(local), password=password,
        first_name='QA', last_name=local.replace('-', ' ').title(),
      )
      AccountProfile.objects.update_or_create(
        user=user,
        defaults={
          'account_status': AccountProfile.AccountStatus.ACTIVE,
          'email_verified': True,
          'account_mode': AccountProfile.AccountMode.PERSONAL,
          'must_change_password': False,
        },
      )
      # `Membership.objects.create` dispara el chequeo real de asientos (V2).
      Membership.objects.create(user=user, business=business, role=role)
    return business

  def _verify_entitlement(self, business) -> None:
    ctx = build_business_context(business)
    ok = (
      ctx.get('_subscription_source') == 'v2'
      and ctx.get('access_allowed')
      and 'appointments' in ctx.get('enabled_services', [])
      and ctx.get('features', {}).get('appointments_core')
    )
    if not ok:
      raise CommandError(
        f'{business.slug}: entitlement inesperado (source={ctx.get("_subscription_source")}, '
        f'access={ctx.get("access_allowed")}, services={ctx.get("enabled_services")}).'
      )

  # ── QA Turnos: catálogo ─────────────────────────────────────────────────────

  def _create_catalog(self, business):
    cats = {
      key: AppointmentCategory.objects.create(business=business, name=name, sort_order=i)
      for i, (key, name) in enumerate([('cortes', 'Cortes'), ('color', 'Color'), ('trat', 'Tratamientos')])
    }
    specs = [
      # key, nombre, categoría, minutos, precio, tipo de seña, valor
      ('corte', 'Corte de pelo', 'cortes', 30, '8000', 'none', '0'),
      ('barba', 'Corte + barba', 'cortes', 45, '11000', 'fixed', '3000'),
      ('color', 'Coloración completa', 'color', 90, '35000', 'percentage', '30'),
      ('mechas', 'Mechas', 'color', 120, '45000', 'fixed', '10000'),
      ('trat', 'Tratamiento capilar', 'trat', 60, '15000', 'percentage', '20'),
    ]
    services = {}
    for i, (key, name, cat, minutes, price, dep_type, dep_value) in enumerate(specs):
      services[key] = self._service(
        business, category=cats[cat], name=name, minutes=minutes, price=price,
        deposit_type=dep_type, deposit_value=dep_value, sort_order=i,
      )

    lucia = AppointmentProfessional.objects.create(
      business=business, name='Lucía QA', description='Color y cortes', sort_order=0,
    )
    martin = AppointmentProfessional.objects.create(
      business=business, name='Martín QA', description='Cortes y tratamientos', sort_order=1,
    )
    lucia.services.set([services['corte'], services['barba'], services['color'], services['mechas']])
    martin.services.set([services['corte'], services['barba'], services['trat']])
    return services, {'lucia': lucia, 'martin': martin}

  def _service(self, business, *, category, name, minutes, price, deposit_type, deposit_value, sort_order=0):
    service = AppointmentService(
      business=business, category=category, name=name, duration_minutes=minutes,
      price=Decimal(price), deposit_type=deposit_type, deposit_value=Decimal(deposit_value), sort_order=sort_order,
    )
    service.full_clean()  # misma regla de seña que el serializer (Slice 7C)
    service.save()
    return service

  def _business_hours(self, business) -> list:
    t = dt.time
    return [(None, wd, t(9), t(19)) for wd in range(0, 5)] + [(None, 5, t(9), t(13))]

  def _bulk_schedules(self, business, rows) -> None:
    AppointmentSchedule.objects.bulk_create([
      AppointmentSchedule(business=business, professional=pro, weekday=wd, start_time=start, end_time=end)
      for pro, wd, start, end in rows
    ])

  def _create_schedules(self, business, pros):
    t = dt.time
    rows = self._business_hours(business)
    rows += [(pros['lucia'], wd, t(9), t(17)) for wd in range(0, 5)]
    rows += [(pros['martin'], wd, t(10), t(19)) for wd in range(1, 5)] + [(pros['martin'], 5, t(10), t(13))]
    self._bulk_schedules(business, rows)

    # Días donde trabajan ambos profesionales (martes a viernes), desde mañana.
    today = self.now.astimezone(self.tz).date()
    candidates = [today + dt.timedelta(days=n) for n in range(1, 30)]
    shared = [d for d in candidates if d.weekday() in (1, 2, 3, 4)]
    days, closed_day = shared[:4], shared[4]
    AppointmentException.objects.create(
      business=business, date=closed_day, is_closed=True, note='Feriado QA (negocio cerrado)',
    )
    return days, closed_day

  # ── Turnos ──────────────────────────────────────────────────────────────────

  def _at(self, day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=self.tz)

  def _phone(self, business, name: str) -> str:
    """Un teléfono estable por persona y negocio (clave del resolver de Customer)."""
    key = (business.pk, name)
    if key not in self.phones:
      self.phones[key] = f'11{5550000 + len(self.phones):08d}'
    return self.phones[key]

  def _appointment(self, business, service, pro, start, *, status, expires_at=None, source='manual', customer):
    phone = self._phone(business, customer)
    # Misma resolución canónica que producción (CUSTOMER 01): reutiliza o crea
    # el Customer por teléfono dentro del Business (ya lockeado por el caller).
    linked = resolve_customer_for_appointment(
      business=business, customer_name=customer, customer_phone=phone, customer_email='',
    )
    return Appointment.objects.create(
      business=business, service=service, professional=pro, customer=linked,
      customer_name=customer, customer_phone=phone, customer_email='',
      start_at=start, end_at=start + dt.timedelta(minutes=service.duration_minutes),
      status=status, expires_at=expires_at, source=source,
      notes='Seed QA',
      service_name=service.name, service_duration_minutes=service.duration_minutes,
      service_price=service.price, deposit_type=service.deposit_type, deposit_value=service.deposit_value,
    )

  def _simulate_approved_payment(self, appointment, seq: int, *, approved_at: dt.datetime):
    """Intento `pending` local + aprobación simulada con el servicio real (sin MP)."""
    pid = uuid.uuid4()
    payment = AppointmentPayment.objects.create(
      id=pid, business=appointment.business, appointment=appointment,
      external_reference=AppointmentPayment.build_external_reference(pid),
      amount=appointment.deposit_amount, status=AppointmentPayment.Status.PENDING,
      provider_preference_id=f'{FAKE_ID_PREFIX}-PREF-{seq}',
    )
    payment_data = {
      'status': 'approved',
      'external_reference': payment.external_reference,
      'transaction_amount': str(payment.amount),
      'currency_id': payment.currency,
      'date_approved': approved_at.isoformat(),
      'metadata': {'appointment_payment_id': str(payment.pk)},
    }
    mismatch = payment_confirmation.validate_provider_payment(payment, payment_data, merchant_user_id=None)
    if mismatch is not None:
      raise CommandError(f'Payload simulado inválido: {mismatch}')
    return payment_confirmation.apply_provider_payment(
      appointment_payment_id=payment.pk, provider_payment_id=f'{FAKE_ID_PREFIX}-PAY-{seq}',
      payment_data=payment_data,
    )

  def _lock_business(self, business) -> None:
    # Mismo orden de locks que booking/admin_mutation: Business primero.
    Business.objects.select_for_update().filter(pk=business.pk).first()

  def _past_days(self, count: int) -> list:
    """Martes a viernes ANTERIORES a hoy (historial de clientes)."""
    today = self.now.astimezone(self.tz).date()
    candidates = [today - dt.timedelta(days=n) for n in range(1, 60)]
    return [d for d in candidates if d.weekday() in (1, 2, 3, 4)][:count]

  def _create_appointments(self, business, s, p, days):
    self._lock_business(business)
    d1, d2, d3, d4 = days
    S = Appointment.Status
    hold = self.now + dt.timedelta(minutes=self.hold_minutes)
    out = []

    def add(label, appt, extra=''):
      appt.refresh_from_db()
      out.append((label, appt, extra))

    # Confirmados
    add('confirmed (manual, sin seña)',
        self._appointment(business, s['corte'], p['lucia'], self._at(d1, 10), status=S.CONFIRMED, customer='Ana Confirmada'))
    add('confirmed (pública, sin seña)',
        self._appointment(business, s['corte'], p['martin'], self._at(d1, 11), status=S.CONFIRMED,
                          source='public', customer='Bruno Confirmado'))
    add('confirmed (manual, tratamiento)',
        self._appointment(business, s['trat'], p['martin'], self._at(d2, 15), status=S.CONFIRMED, customer='Carla Confirmada'))
    add('cancelled',
        self._appointment(business, s['corte'], p['lucia'], self._at(d2, 12), status=S.CANCELLED, customer='Diego Cancelado'))

    # pending_payment con hold vigente (ocupan el slot hasta `expires_at`)
    add('pending_payment (seña fija, hold vigente)',
        self._appointment(business, s['barba'], p['lucia'], self._at(d2, 10), status=S.PENDING_PAYMENT,
                          expires_at=hold, source='public', customer='Elena Pendiente'))
    add('pending_payment (seña %, hold vigente)',
        self._appointment(business, s['color'], p['lucia'], self._at(d3, 14), status=S.PENDING_PAYMENT,
                          expires_at=hold, source='public', customer='Federico Pendiente'))

    # Vencidos: uno materializado, otro solo "efectivo" (status en DB = pending_payment)
    add('expired (materializado en DB)',
        self._appointment(business, s['barba'], p['martin'], self._at(d1, 16), status=S.EXPIRED,
                          expires_at=self.now - dt.timedelta(hours=2), source='public', customer='Gabriela Vencida'))
    add('pending_payment con hold vencido (effective_status=expired)',
        self._appointment(business, s['barba'], p['martin'], self._at(d4, 12), status=S.PENDING_PAYMENT,
                          expires_at=self.now - dt.timedelta(minutes=5), source='public', customer='Hernán Vencido'))

    # Pago aprobado simulado → confirma el turno (servicio real, payload fake)
    approved = self._appointment(business, s['mechas'], p['lucia'], self._at(d4, 10), status=S.PENDING_PAYMENT,
                                 expires_at=hold, source='public', customer='Inés Pagó')
    outcome = self._simulate_approved_payment(approved, 1, approved_at=self.now)
    if outcome.result != payment_confirmation.Result.APPLIED:
      raise CommandError(f'Pago aprobado simulado no se aplicó: {outcome}')
    add('confirmed vía pago aprobado (simulado)', approved, 'payment=approved')

    # Aprobado DESPUÉS del vencimiento del hold → requires_review (turno queda expired)
    review = self._appointment(business, s['trat'], p['martin'], self._at(d3, 11), status=S.PENDING_PAYMENT,
                               expires_at=self.now - dt.timedelta(minutes=30), source='public', customer='Juan Revisión')
    outcome = self._simulate_approved_payment(review, 2, approved_at=self.now)
    if outcome.result != payment_confirmation.Result.REQUIRES_REVIEW:
      raise CommandError(f'requires_review simulado no se generó: {outcome}')
    add('expired + payment requires_review (approved_after_expiry)', review, 'payment=requires_review')

    # Historial pasado (ficha de Clientes): Ana es clienta recurrente con
    # próximo turno (confirmed d1) + completed, no_show y cancelled pasados.
    p1, p2, p3 = self._past_days(3)
    add('historial: completed (Ana, cliente recurrente)',
        self._appointment(business, s['corte'], p['lucia'], self._at(p3, 10), status=S.COMPLETED, customer='Ana Confirmada'))
    add('historial: no_show (Ana)',
        self._appointment(business, s['barba'], p['martin'], self._at(p2, 11), status=S.NO_SHOW, customer='Ana Confirmada'))
    add('historial: cancelled (Ana)',
        self._appointment(business, s['corte'], p['lucia'], self._at(p2, 15), status=S.CANCELLED, customer='Ana Confirmada'))
    add('historial: completed (Ana, último turno)',
        self._appointment(business, s['color'], p['lucia'], self._at(p1, 10), status=S.COMPLETED, customer='Ana Confirmada'))
    add('historial: completed (Carla)',
        self._appointment(business, s['trat'], p['martin'], self._at(p1, 15), status=S.COMPLETED, customer='Carla Confirmada'))
    return out

  # ── QA Turnos Viewer: copia mínima ──────────────────────────────────────────

  def _create_viewer_fixtures(self, business, days):
    self._lock_business(business)
    d1, d2 = days[0], days[1]
    S = Appointment.Status
    category = AppointmentCategory.objects.create(business=business, name='Cortes')
    # Sin profesionales: los turnos son "del negocio" (professional=None).
    service = self._service(
      business, category=category, name='Corte de pelo', minutes=30, price='8000',
      deposit_type='none', deposit_value='0',
    )
    self._bulk_schedules(business, self._business_hours(business))
    out = []
    for label, appt in [
      ('confirmed', self._appointment(business, service, None, self._at(d1, 10), status=S.CONFIRMED, customer='Vera Confirmada')),
      ('confirmed (pública)', self._appointment(business, service, None, self._at(d1, 11), status=S.CONFIRMED,
                                                source='public', customer='Walter Confirmado')),
      ('cancelled', self._appointment(business, service, None, self._at(d2, 10), status=S.CANCELLED, customer='Ximena Cancelada')),
    ]:
      appt.refresh_from_db()
      out.append((label, appt, ''))
    return out

  # ── Resumen ─────────────────────────────────────────────────────────────────

  def _print_appointments(self, business, appointments) -> None:
    w = self.stdout.write
    for label, appt, extra in appointments:
      local = appt.start_at.astimezone(self.tz)
      pro = appt.professional.name if appt.professional_id else '(negocio)'
      w(f'    {local:%d/%m %H:%M}  {pro:<10} {appt.service_name:<20} status={appt.status:<15} '
        f'effective={appt.effective_status():<15} {extra}')
      w(f'        {label}')
      w(f'        día:     {FRONT}/app/turnos/turnos?date={local.date().isoformat()}&appointment={appt.pk}')
      w(f'        público: {build_public_booking_url(business.slug)}?booking={appt.public_token}')

  def _print_tenant(self, title, tenant, business, appointments) -> None:
    w = self.stdout.write
    first_day = appointments[0][1].start_at.astimezone(self.tz).date()
    w('\n' + self.style.SUCCESS(title))
    w(f'  Business:       {business.name} (slug={business.slug}, tz={business.timezone}, '
      f'SubscriptionV2 manual/{PLAN_CODE})')
    for local, role in tenant['members']:
      w(f'  {role:<8} email: {qa_email(local)}')
    w(f'  Panel:          {FRONT}/app/turnos')
    w(f'  Clientes:       {FRONT}/app/clientes ({business.customers.count()} vinculados a turnos)')
    w(f'  Semana:         {FRONT}/app/turnos/turnos?date={first_day.isoformat()}')
    w(f'  Página pública: {build_public_booking_url(business.slug)}')
    w('  Turnos:')
    self._print_appointments(business, appointments)

  def _print_summary(self, main, main_appts, viewer, viewer_appts, password, generated, closed_day):
    w = self.stdout.write
    w('\n' + '=' * 72)
    w(self.style.SUCCESS('SEED QA TURNOS LISTO'))
    w('=' * 72)
    w(f'Login: {FRONT}/entrar')
    if generated:
      w(self.style.WARNING(f'Password (generada en esta corrida, no se guarda en ningún lado): {password}'))
      w(f'Para fijarla: {PASSWORD_ENV}=... o --password ...')
    else:
      w(f'Password: la indicada por --password / {PASSWORD_ENV}')

    self._print_tenant('QA TURNOS', MAIN, main, main_appts)
    w(f'  Excepción:      negocio cerrado el {closed_day.isoformat()}')
    w(f'  Otras:          {FRONT}/app/turnos/servicios · /servicios/categorias · /profesionales · '
      f'/horarios · /configuracion')
    self._print_tenant('QA TURNOS VIEWER', VIEWER, viewer, viewer_appts)

    w('\nNota: sin MercadoPagoConnection → el checkout de seña desde la página pública responde '
      '"payment_unavailable" (esperado; no se toca MP real).')
    w('Reset: python manage.py seed_turnos_qa --reset')
    w('=' * 72 + '\n')
