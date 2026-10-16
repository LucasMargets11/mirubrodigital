import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone as dj_timezone


class AppointmentCategory(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='appointment_categories', on_delete=models.CASCADE)
  name = models.CharField(max_length=100)
  description = models.CharField(max_length=255, blank=True)
  is_active = models.BooleanField(default=True)
  sort_order = models.PositiveIntegerField(default=0)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['sort_order', 'name']
    verbose_name = 'Categoría de Turnos'
    verbose_name_plural = 'Categorías de Turnos'
    constraints = [
      models.UniqueConstraint(
        fields=['business', 'name'],
        name='unique_appointment_category_per_business'
      )
    ]
    indexes = [
      models.Index(fields=['business', 'sort_order', 'name']),
    ]

  def __str__(self) -> str:
    return f"{self.name} ({self.business_id})"


class AppointmentProfessional(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='appointment_professionals', on_delete=models.CASCADE)
  name = models.CharField(max_length=150)
  description = models.CharField(max_length=500, blank=True)
  phone = models.CharField(max_length=30, blank=True)
  email = models.EmailField(blank=True)
  services = models.ManyToManyField('appointments.AppointmentService', related_name='professionals', blank=True)
  is_active = models.BooleanField(default=True)
  sort_order = models.PositiveIntegerField(default=0)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['sort_order', 'name']
    verbose_name = 'Profesional de Turnos'
    verbose_name_plural = 'Profesionales de Turnos'
    constraints = [
      models.UniqueConstraint(
        fields=['business', 'name'],
        name='unique_appointment_professional_per_business'
      )
    ]
    indexes = [
      models.Index(fields=['business', 'sort_order', 'name']),
    ]

  def __str__(self) -> str:
    return f"{self.name} ({self.business_id})"


class AppointmentSchedule(models.Model):
  class Weekday(models.IntegerChoices):
    MONDAY = 0, 'Lunes'
    TUESDAY = 1, 'Martes'
    WEDNESDAY = 2, 'Miércoles'
    THURSDAY = 3, 'Jueves'
    FRIDAY = 4, 'Viernes'
    SATURDAY = 5, 'Sábado'
    SUNDAY = 6, 'Domingo'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='appointment_schedules', on_delete=models.CASCADE)
  professional = models.ForeignKey(
    'appointments.AppointmentProfessional',
    related_name='schedules',
    null=True,
    blank=True,
    on_delete=models.CASCADE,
  )
  weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
  start_time = models.TimeField()
  end_time = models.TimeField()
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['weekday', 'start_time']
    verbose_name = 'Horario de Turnos'
    verbose_name_plural = 'Horarios de Turnos'
    constraints = [
      models.CheckConstraint(check=models.Q(start_time__lt=models.F('end_time')), name='appointment_schedule_start_before_end'),
    ]
    indexes = [
      models.Index(fields=['business', 'professional', 'weekday']),
    ]

  def __str__(self) -> str:
    who = self.professional.name if self.professional_id else 'Negocio'
    return f"{who} - {self.get_weekday_display()} {self.start_time}-{self.end_time} ({self.business_id})"


class AppointmentException(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='appointment_exceptions', on_delete=models.CASCADE)
  professional = models.ForeignKey(
    'appointments.AppointmentProfessional',
    related_name='exceptions',
    null=True,
    blank=True,
    on_delete=models.CASCADE,
  )
  date = models.DateField()
  is_closed = models.BooleanField(default=False)
  start_time = models.TimeField(null=True, blank=True)
  end_time = models.TimeField(null=True, blank=True)
  note = models.CharField(max_length=255, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['-date']
    verbose_name = 'Excepción de Turnos'
    verbose_name_plural = 'Excepciones de Turnos'
    constraints = [
      models.CheckConstraint(
        check=(
          models.Q(is_closed=True, start_time__isnull=True, end_time__isnull=True)
          | models.Q(is_closed=False, start_time__isnull=False, end_time__isnull=False, start_time__lt=models.F('end_time'))
        ),
        name='appointment_exception_valid_hours',
      ),
    ]
    indexes = [
      models.Index(fields=['business', 'professional', 'date']),
    ]

  def __str__(self) -> str:
    who = self.professional.name if self.professional_id else 'Negocio'
    status = 'Cerrado' if self.is_closed else f"{self.start_time}-{self.end_time}"
    return f"{who} - {self.date} ({status})"


class AppointmentService(models.Model):
  class DepositType(models.TextChoices):
    NONE = 'none', 'Sin seña'
    FIXED = 'fixed', 'Monto fijo'
    PERCENTAGE = 'percentage', 'Porcentaje'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='appointment_services', on_delete=models.CASCADE)
  category = models.ForeignKey(
    'appointments.AppointmentCategory',
    related_name='services',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  name = models.CharField(max_length=255)
  description = models.CharField(max_length=1000, blank=True)
  duration_minutes = models.PositiveIntegerField()
  price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  deposit_type = models.CharField(max_length=16, choices=DepositType.choices, default=DepositType.NONE)
  deposit_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  is_active = models.BooleanField(default=True)
  sort_order = models.PositiveIntegerField(default=0)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['sort_order', 'name']
    verbose_name = 'Servicio de Turnos'
    verbose_name_plural = 'Servicios de Turnos'
    constraints = [
      models.CheckConstraint(check=models.Q(duration_minutes__gt=0), name='appointment_service_duration_positive'),
      models.CheckConstraint(check=models.Q(price__gte=0), name='appointment_service_price_non_negative'),
      models.CheckConstraint(check=models.Q(deposit_value__gte=0), name='appointment_service_deposit_non_negative'),
    ]
    indexes = [
      models.Index(fields=['business', 'sort_order', 'name']),
      models.Index(fields=['business', 'category']),
    ]

  def __str__(self) -> str:
    return f"{self.name} ({self.business_id})"

  def clean(self):
    # Slice 7C: misma regla canónica que `AppointmentServiceSerializer`. Sin
    # CheckConstraint: los servicios legacy `fixed=0` no se migran en silencio
    # (la reserva pública los rechaza, ver `services.booking`).
    from django.core.exceptions import ValidationError

    from .services.deposit import deposit_config_error

    super().clean()
    error = deposit_config_error(price=self.price, deposit_type=self.deposit_type, deposit_value=self.deposit_value)
    if error:
      raise ValidationError({'deposit_value': error})


class AppointmentQuerySet(models.QuerySet):
  def occupying(self, *, now=None):
    """Turnos que ocupan disponibilidad EN ESTE INSTANTE (`now`).

    Definición central y única de "ocupación" (Slice 4B): un turno ocupa un
    horario si está `confirmed`, o si está `pending_payment` con un hold
    todavía vigente (`expires_at` en el futuro). Un `pending_payment` vencido
    libera el horario de inmediato, aunque el campo `status` todavía no haya
    sido actualizado físicamente a `expired` por el management command
    (ver `services.expiration`).

    Reutilizada por `services.availability` (cálculo de slots) y
    `services.booking` (chequeo de solapamiento) para no duplicar esta regla.
    """
    now = now or dj_timezone.now()
    return self.filter(
      Q(status=Appointment.Status.CONFIRMED)
      | Q(status=Appointment.Status.PENDING_PAYMENT, expires_at__gt=now)
    )


class Appointment(models.Model):
  """Turno reservado (Slice 3A/4B).

  Guarda un snapshot del servicio (`service_name`, `service_duration_minutes`,
  `service_price`, `deposit_type`, `deposit_value`) tomado al momento de crear
  o reprogramar el turno, para que cambios posteriores en `AppointmentService`
  no alteren turnos ya existentes.
  """

  class Status(models.TextChoices):
    PENDING_PAYMENT = 'pending_payment', 'Pendiente de pago'
    CONFIRMED = 'confirmed', 'Confirmado'
    COMPLETED = 'completed', 'Completado'
    CANCELLED = 'cancelled', 'Cancelado'
    NO_SHOW = 'no_show', 'No asistió'
    EXPIRED = 'expired', 'Vencido'

  class Source(models.TextChoices):
    MANUAL = 'manual', 'Manual'
    PUBLIC = 'public', 'Reserva pública'

  # Estados que, en principio, ocupan disponibilidad. La regla real y
  # completa (que también considera el vencimiento de `pending_payment`)
  # vive en `AppointmentQuerySet.occupying` — no duplicar esta lista en
  # otro lugar del código.
  OCCUPYING_STATUSES = (Status.CONFIRMED, Status.PENDING_PAYMENT)

  objects = AppointmentQuerySet.as_manager()

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  public_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
  business = models.ForeignKey('business.Business', related_name='appointments', on_delete=models.CASCADE)
  service = models.ForeignKey('appointments.AppointmentService', related_name='appointments', on_delete=models.PROTECT)
  professional = models.ForeignKey(
    'appointments.AppointmentProfessional',
    related_name='appointments',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )

  # Turnos CUSTOMER 01: identidad canónica/viva del cliente (mismo
  # `Business`, ver `services.customer_link`). NULL en turnos legacy o sin
  # teléfono utilizable. Los `customer_*` siguen siendo snapshots históricos
  # del turno: nunca se reemplazan por los datos actuales del `Customer`.
  customer = models.ForeignKey(
    'customers.Customer',
    related_name='appointments',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  customer_name = models.CharField(max_length=150)
  customer_phone = models.CharField(max_length=30)
  customer_email = models.EmailField(blank=True)

  start_at = models.DateTimeField()
  end_at = models.DateTimeField()

  status = models.CharField(max_length=16, choices=Status.choices, default=Status.CONFIRMED)
  # Vencimiento del hold de `pending_payment` (Slice 4B). NULL para cualquier
  # otro estado. Ver `AppointmentQuerySet.occupying` y `effective_status`.
  expires_at = models.DateTimeField(null=True, blank=True)
  notes = models.CharField(max_length=1000, blank=True)
  source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)

  # Snapshot del servicio al momento de crear/reprogramar el turno.
  service_name = models.CharField(max_length=255)
  service_duration_minutes = models.PositiveIntegerField()
  service_price = models.DecimalField(max_digits=12, decimal_places=2)
  deposit_type = models.CharField(max_length=16, choices=AppointmentService.DepositType.choices)
  deposit_value = models.DecimalField(max_digits=12, decimal_places=2)

  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['-start_at']
    verbose_name = 'Turno'
    verbose_name_plural = 'Turnos'
    constraints = [
      models.CheckConstraint(check=models.Q(start_at__lt=models.F('end_at')), name='appointment_start_before_end'),
      models.CheckConstraint(
        check=~models.Q(status='pending_payment') | models.Q(expires_at__isnull=False),
        name='appointment_pending_payment_requires_expires_at',
      ),
    ]
    indexes = [
      models.Index(fields=['business', 'professional', 'start_at']),
      models.Index(fields=['business', 'status', 'start_at']),
      models.Index(fields=['business', 'start_at']),
    ]

  def __str__(self) -> str:
    return f"{self.customer_name} - {self.start_at.isoformat()} ({self.business_id})"

  def effective_status(self, *, now=None) -> str:
    """Estado "real" considerando el vencimiento del hold.

    Un `pending_payment` con `expires_at` en el pasado se considera
    `expired` aunque el campo `status` en la base todavía no haya sido
    actualizado por `expire_appointment_holds` (Slice 4B, punto 8/11).
    """
    now = now or dj_timezone.now()
    if self.status == self.Status.PENDING_PAYMENT and self.expires_at and self.expires_at <= now:
      return self.Status.EXPIRED
    return self.status

  @property
  def deposit_amount(self) -> Decimal:
    """Monto de seña a cobrar, calculado a partir del snapshot del turno.

    Ver `services.deposit.compute_deposit_amount` (misma fórmula, reusada
    también al momento de crear la reserva).
    """
    from .services.deposit import compute_deposit_amount

    return compute_deposit_amount(
      price=self.service_price, deposit_type=self.deposit_type, deposit_value=self.deposit_value,
    )


# Moneda de las señas de Turnos. Misma moneda canónica que el otro flujo
# merchant-side existente (Tips: `TipTransaction.currency` default 'ARS',
# `currency_id='ARS'` en su Preference). Sin soporte multi-moneda (Slice 6A).
APPOINTMENT_PAYMENT_CURRENCY = 'ARS'

EXTERNAL_REFERENCE_PREFIX = 'APPOINTMENT_PAYMENT-'


class AppointmentPayment(models.Model):
  """Intento de cobro de la seña de un `Appointment` vía Mercado Pago (Slice 6A).

  Dominio de Turnos (no de `merchant_payments`): toda la interacción con MP
  pasa por `apps.merchant_payments.services`, que solo conoce la conexión
  del Business. Un turno puede acumular varios intentos a lo largo de su
  vida, pero como máximo UNO "activo" (`ACTIVE_STATUSES`) a la vez —
  garantizado por la constraint parcial `appointment_payment_single_active`.

  No guarda payloads de Mercado Pago: solo ids, URL de checkout y códigos
  internos cortos de error.
  """

  class Provider(models.TextChoices):
    MERCADOPAGO = 'mercadopago', 'Mercado Pago'

  class Status(models.TextChoices):
    # Fila reservada localmente, Preference todavía no pedida/confirmada.
    CREATING = 'creating', 'Creando'
    # Preference creada en MP; checkout_url disponible.
    PENDING = 'pending', 'Pendiente'
    APPROVED = 'approved', 'Aprobado'
    REJECTED = 'rejected', 'Rechazado'
    CANCELLED = 'cancelled', 'Cancelado'
    # Fallo definitivo SIN Preference remota (conexión MP inexistente, MP
    # rechazó el request, ...). Terminal: se puede iniciar otro intento.
    ERROR = 'error', 'Error'
    # Resultado incierto: la Preference PUDO haberse creado en MP (timeout,
    # 5xx, respuesta incompleta). Bloquea nuevos intentos para el turno
    # hasta reconciliación manual (ver docs de Slice 6A).
    UNCERTAIN = 'uncertain', 'Incierto'
    # Slice 6B: Mercado Pago APROBÓ el pago (el dinero se cobró), pero NO se
    # aplicó automáticamente al turno (aprobado fuera de la ventana del hold,
    # slot ocupado por otro turno, turno cancelado/confirmado por otra vía,
    # ...). El motivo queda en `review_reason`. Terminal hasta resolución
    # manual (refund: slice posterior). `APPROVED` significa siempre
    # "aprobado Y aplicado al turno".
    REQUIRES_REVIEW = 'requires_review', 'Requiere revisión'

  # Estados que impiden crear otro intento para el mismo turno.
  ACTIVE_STATUSES = (Status.CREATING, Status.PENDING, Status.UNCERTAIN)
  # Estados en los que el dinero fue efectivamente cobrado por el provider.
  CAPTURED_STATUSES = (Status.APPROVED, Status.REQUIRES_REVIEW)

  class ReviewReason(models.TextChoices):
    APPROVED_AFTER_EXPIRY = 'approved_after_expiry', 'Aprobado después del vencimiento del hold'
    APPROVAL_TIME_UNKNOWN = 'approval_time_unknown', 'Fecha de aprobación no disponible'
    SLOT_CONFLICT = 'slot_conflict', 'El horario fue ocupado por otro turno'
    # Turno ya confirmado sin este pago (otro intento aprobado, alta manual...).
    APPOINTMENT_ALREADY_CONFIRMED = 'appointment_already_confirmed', 'El turno ya estaba confirmado'
    # Turno cancelado / completado / no_show: nunca se reabre automáticamente.
    APPOINTMENT_NOT_PAYABLE = 'appointment_not_payable', 'El turno ya no admitía el pago'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  # Mismo criterio que `TipTransaction` / `Appointment.business`: CASCADE.
  # Los turnos nunca se borran físicamente desde la app (se cancelan).
  business = models.ForeignKey('business.Business', related_name='appointment_payments', on_delete=models.CASCADE)
  appointment = models.ForeignKey(
    'appointments.Appointment', related_name='payments', on_delete=models.CASCADE,
  )
  provider = models.CharField(max_length=32, choices=Provider.choices, default=Provider.MERCADOPAGO)
  # `APPOINTMENT_PAYMENT-<id.hex>`. Generada server-side; clave de routing
  # del webhook (`flow=appointment&ref=...`, Slice 6B).
  external_reference = models.CharField(max_length=64, unique=True)
  amount = models.DecimalField(max_digits=12, decimal_places=2)
  currency = models.CharField(max_length=8, default=APPOINTMENT_PAYMENT_CURRENCY)
  status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATING)
  provider_preference_id = models.CharField(max_length=128, null=True, blank=True)
  provider_payment_id = models.CharField(max_length=128, null=True, blank=True)
  checkout_url = models.URLField(max_length=512, null=True, blank=True)
  provider_status = models.CharField(max_length=32, blank=True)
  # Código interno corto (p.ej. `mp_not_connected`, `mp_uncertain:504`).
  # Nunca tokens ni payloads.
  failure_reason = models.CharField(max_length=64, blank=True)
  # Solo para `requires_review` (Slice 6B). Ver `ReviewReason`.
  review_reason = models.CharField(max_length=32, choices=ReviewReason.choices, blank=True)
  # Fecha autoritativa de aprobación informada por Mercado Pago (`date_approved`).
  paid_at = models.DateTimeField(null=True, blank=True)
  refunded_at = models.DateTimeField(null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['-created_at']
    verbose_name = 'Pago de Turno'
    verbose_name_plural = 'Pagos de Turnos'
    constraints = [
      models.CheckConstraint(check=models.Q(amount__gt=0), name='appointment_payment_amount_positive'),
      models.UniqueConstraint(
        fields=['appointment'],
        condition=models.Q(status__in=['creating', 'pending', 'uncertain']),
        name='appointment_payment_single_active',
      ),
      # Slice 6B: un mismo pago de Mercado Pago nunca se asocia a dos intentos
      # (ni puede confirmar dos turnos).
      models.UniqueConstraint(
        fields=['provider', 'provider_payment_id'],
        condition=models.Q(provider_payment_id__isnull=False),
        name='appointment_payment_unique_provider_payment',
      ),
      # Dinero cobrado ⇒ siempre se sabe qué pago del provider lo respalda.
      models.CheckConstraint(
        check=~models.Q(status__in=['approved', 'requires_review']) | models.Q(provider_payment_id__isnull=False),
        name='appointment_payment_captured_has_provider_id',
      ),
    ]
    indexes = [
      models.Index(fields=['business', 'created_at']),
      models.Index(fields=['appointment', 'status']),
    ]

  def __str__(self) -> str:
    return f"{self.external_reference} · {self.status}"

  @staticmethod
  def build_external_reference(payment_id: uuid.UUID) -> str:
    return f'{EXTERNAL_REFERENCE_PREFIX}{payment_id.hex}'
