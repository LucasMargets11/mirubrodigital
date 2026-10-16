import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Customer(models.Model):
  class CustomerType(models.TextChoices):
    INDIVIDUAL = 'individual', 'Persona'
    COMPANY = 'company', 'Empresa'

  class DocumentType(models.TextChoices):
    DNI = 'dni', 'DNI'
    CUIT = 'cuit', 'CUIT'
    PASSPORT = 'passport', 'Pasaporte'
    OTHER = 'other', 'Otro'

  class TaxCondition(models.TextChoices):
    CONSUMER = 'consumer', 'Consumidor Final'
    REGISTERED = 'registered', 'Responsable Inscripto'
    MONOTAX = 'monotax', 'Monotributo'
    EXEMPT = 'exempt', 'Exento'
    OTHER = 'other', 'Otro'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='customers', on_delete=models.CASCADE)
  name = models.CharField(max_length=255)
  type = models.CharField(max_length=16, choices=CustomerType.choices, default=CustomerType.INDIVIDUAL)
  doc_type = models.CharField(max_length=32, choices=DocumentType.choices, blank=True, default='')
  doc_number = models.CharField(max_length=64, blank=True, default='')
  tax_condition = models.CharField(max_length=32, choices=TaxCondition.choices, blank=True, default='')
  email = models.EmailField(blank=True)
  phone = models.CharField(max_length=64, blank=True)
  address_line = models.CharField(max_length=255, blank=True)
  city = models.CharField(max_length=128, blank=True)
  province = models.CharField(max_length=128, blank=True)
  postal_code = models.CharField(max_length=32, blank=True)
  country = models.CharField(max_length=64, blank=True)
  note = models.TextField(blank=True)
  tags = models.JSONField(default=list, blank=True)
  is_active = models.BooleanField(default=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['name']
    indexes = [
      models.Index(fields=['business', 'name']),
      models.Index(fields=['business', 'email']),
      models.Index(fields=['business', 'phone']),
      models.Index(fields=['business', 'doc_number']),
    ]
    constraints = [
      models.UniqueConstraint(
        fields=['business', 'doc_type', 'doc_number'],
        condition=Q(doc_type__gt='') & Q(doc_number__gt=''),
        name='customer_unique_document_per_business',
      )
    ]

  def __str__(self) -> str:
    return f"{self.name} ({self.business_id})"


class CustomerNote(models.Model):
  """Nota interna del equipo sobre un Customer (CUSTOMER 04C).

  Interna del Business: nunca se expone al cliente. No es `Appointment.notes`
  ni `Customer.note` (campo libre del alta). Texto plano, hard delete.

  `business` se denormaliza (como el resto de las entidades tenant) para
  filtrar siempre por Business; `save()` garantiza que coincide con el del
  Customer. `created_at` es el `occurred_at` natural si en el futuro la
  timeline incluye `type="note"` (se derivaría al consultar, sin duplicar).
  """

  BODY_MAX_LENGTH = 2000

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='customer_notes', on_delete=models.CASCADE)
  customer = models.ForeignKey(Customer, related_name='internal_notes', on_delete=models.CASCADE)
  # Si se borra el usuario la nota queda (autor anónimo): es contexto del cliente, no del autor.
  author = models.ForeignKey(
    settings.AUTH_USER_MODEL, related_name='customer_notes', on_delete=models.SET_NULL, null=True, blank=True,
  )
  body = models.TextField()
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['-created_at', '-id']
    indexes = [
      models.Index(fields=['business', 'customer', '-created_at'], name='customer_note_feed_idx'),
    ]
    constraints = [
      models.CheckConstraint(check=~Q(body=''), name='customer_note_body_not_empty'),
    ]

  def save(self, *args, **kwargs):
    # Tenant safety: una nota nunca puede apuntar a un Customer de otro Business.
    if self.customer_id is not None:
      customer_business_id = self.customer.business_id
      if self.business_id is None:
        self.business_id = customer_business_id
      elif self.business_id != customer_business_id:
        raise ValueError('CustomerNote.business must match customer.business.')
    super().save(*args, **kwargs)

  def __str__(self) -> str:
    return f"Note {self.pk} ({self.customer_id})"


class CustomerReminder(models.Model):
  """Recordatorio interno del equipo sobre un Customer (CUSTOMER 07A).

  Acción futura que alguien del Business tiene que hacer ("Llamar mañana a
  las 16"). NO es un mensaje al cliente ni una `BusinessNotification` (esa
  registra eventos ya ocurridos). Nunca se envía nada al cliente. Los
  manuales cambian solo por acción del equipo; los automáticos (`source` !=
  manual, CUSTOMER 07B) los crea/mueve/cancela el ciclo de vida del turno.

  - `remind_at` es timezone-aware; la UI lo muestra en `Business.timezone`.
  - "Vencido" es derivado (`is_overdue`): pending con `remind_at` pasado. No
    hay un estado persistido `overdue` ni nada que mute la fila al vencer.
  - `completed` y `cancelled` son finales (MVP: no se reabren). Sin hard
    delete desde la API: cancelar conserva la trazabilidad.
  - `appointment` opcional: mismo Business (guarda en `save()`) y, al
    vincularlo, el mismo Customer si el turno tiene uno (serializer).
  """

  TITLE_MAX_LENGTH = 200
  DESCRIPTION_MAX_LENGTH = 2000

  class Status(models.TextChoices):
    PENDING = 'pending', 'Pendiente'
    COMPLETED = 'completed', 'Completado'
    CANCELLED = 'cancelled', 'Cancelado'

  class Source(models.TextChoices):
    """Origen (CUSTOMER 07B). Los automáticos los administra
    `appointments/services/reminder_automation.py`; no se editan a mano."""
    MANUAL = 'manual', 'Manual'
    APPOINTMENT_UPCOMING = 'appointment_upcoming', 'Antes del turno'
    NO_SHOW_FOLLOWUP = 'no_show_followup', 'Seguimiento por inasistencia'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='customer_reminders', on_delete=models.CASCADE)
  customer = models.ForeignKey(Customer, related_name='reminders', on_delete=models.CASCADE)
  # Si se borra el turno el recordatorio queda (sin vínculo): sigue siendo una tarea del cliente.
  appointment = models.ForeignKey(
    'appointments.Appointment', related_name='customer_reminders', on_delete=models.SET_NULL, null=True, blank=True,
  )
  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL, related_name='customer_reminders', on_delete=models.SET_NULL, null=True, blank=True,
  )
  title = models.CharField(max_length=TITLE_MAX_LENGTH)
  description = models.TextField(blank=True, default='')
  remind_at = models.DateTimeField()
  status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
  completed_at = models.DateTimeField(null=True, blank=True)
  source = models.CharField(max_length=32, choices=Source.choices, default=Source.MANUAL)
  # Identidad del evento que originó un automático (idempotencia, CUSTOMER 07B):
  # "appointment_upcoming:<appt>:<start_at UTC>" / "no_show_followup:<appt>".
  # Único por Business; NULL en los manuales.
  automation_key = models.CharField(max_length=128, null=True, blank=True)
  # Cuándo se generó el aviso interno (`BusinessNotification`) al llegar
  # `remind_at` (CUSTOMER 07C). NO es un estado: el recordatorio sigue
  # `pending` hasta que alguien lo complete/cancele. Nunca se resetea: un
  # recordatorio produce como máximo un aviso.
  notified_at = models.DateTimeField(null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['remind_at', 'id']
    indexes = [
      models.Index(fields=['business', 'customer', 'status', 'remind_at'], name='customer_reminder_feed_idx'),
      # Para CUSTOMER 07B (recordatorios vencidos/por vencer de todo el sistema).
      models.Index(fields=['status', 'remind_at'], name='customer_reminder_due_idx'),
      # Barrido de avisos (CUSTOMER 07C): solo pendientes todavía no avisados.
      models.Index(
        fields=['remind_at'],
        condition=Q(status='pending', notified_at__isnull=True),
        name='customer_reminder_dispatch_idx',
      ),
    ]
    constraints = [
      models.CheckConstraint(check=~Q(title=''), name='customer_reminder_title_not_empty'),
      models.CheckConstraint(
        check=(Q(status='completed') & Q(completed_at__isnull=False)) | (~Q(status='completed') & Q(completed_at__isnull=True)),
        name='customer_reminder_completed_at_matches_status',
      ),
      models.CheckConstraint(
        check=(Q(source='manual') & Q(automation_key__isnull=True)) | (~Q(source='manual') & Q(automation_key__isnull=False)),
        name='customer_reminder_automation_key_matches_source',
      ),
      models.UniqueConstraint(
        fields=['business', 'automation_key'],
        condition=Q(automation_key__isnull=False),
        name='customer_reminder_unique_automation_key',
      ),
    ]

  @staticmethod
  def appointment_mismatch(customer: Customer, appointment) -> str | None:
    """Motivo por el que `appointment` no puede colgarse de `customer` (o None)."""
    if appointment.business_id != customer.business_id:
      return 'business'
    if appointment.customer_id is not None and appointment.customer_id != customer.pk:
      return 'customer'
    return None

  @property
  def is_automatic(self) -> bool:
    return self.source != self.Source.MANUAL

  def is_overdue(self, *, now=None) -> bool:
    from django.utils import timezone as dj_timezone

    now = now or dj_timezone.now()
    return self.status == self.Status.PENDING and self.remind_at < now

  def save(self, *args, **kwargs):
    # Tenant safety: nunca un Customer ni un turno de otro Business.
    if self.customer_id is not None:
      customer_business_id = self.customer.business_id
      if self.business_id is None:
        self.business_id = customer_business_id
      elif self.business_id != customer_business_id:
        raise ValueError('CustomerReminder.business must match customer.business.')
      # Solo el Business es invariante: el Customer del turno puede cambiar
      # después (CUSTOMER 05) y eso no debe romper completar/cancelar. El
      # match de Customer se valida al vincular (serializer).
      if self.appointment_id is not None and self.appointment.business_id != customer_business_id:
        raise ValueError('CustomerReminder.appointment must belong to the same business.')
    super().save(*args, **kwargs)

  def __str__(self) -> str:
    return f"Reminder {self.pk} ({self.customer_id}, {self.status})"


class CustomerReminderAutomationSettings(models.Model):
  """Reglas de recordatorios internos automáticos por Business (CUSTOMER 07B).

  Arrancan APAGADAS: sin fila = todo deshabilitado con los defaults (no se
  crea la fila al leer). Solo generan `CustomerReminder` internos; nunca
  envían nada al cliente. Los switches gobiernan la CREACIÓN: un automático
  ya creado se sigue moviendo/cancelando con su turno aunque luego se apague.
  """

  APPOINTMENT_HOURS_MIN, APPOINTMENT_HOURS_MAX = 1, 168
  NO_SHOW_HOURS_MIN, NO_SHOW_HOURS_MAX = 1, 720
  DEFAULT_APPOINTMENT_HOURS_BEFORE = 24
  DEFAULT_NO_SHOW_DELAY_HOURS = 24

  business = models.OneToOneField(
    'business.Business', related_name='customer_reminder_automation', on_delete=models.CASCADE,
  )
  appointment_reminder_enabled = models.BooleanField(default=False)
  appointment_reminder_hours_before = models.PositiveSmallIntegerField(default=DEFAULT_APPOINTMENT_HOURS_BEFORE)
  no_show_followup_enabled = models.BooleanField(default=False)
  no_show_followup_delay_hours = models.PositiveSmallIntegerField(default=DEFAULT_NO_SHOW_DELAY_HOURS)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    constraints = [
      models.CheckConstraint(
        check=Q(appointment_reminder_hours_before__gte=1, appointment_reminder_hours_before__lte=168),
        name='reminder_automation_hours_before_range',
      ),
      models.CheckConstraint(
        check=Q(no_show_followup_delay_hours__gte=1, no_show_followup_delay_hours__lte=720),
        name='reminder_automation_no_show_delay_range',
      ),
    ]

  @classmethod
  def for_business(cls, business) -> 'CustomerReminderAutomationSettings':
    """Fila del Business o una instancia NO guardada con los defaults (apagada)."""
    existing = cls.objects.filter(business=business).first()
    return existing if existing is not None else cls(business=business)

  def __str__(self) -> str:
    return f"ReminderAutomation(business={self.business_id})"


class CustomerCommunicationSettings(models.Model):
  """Configuración de comunicaciones del Business hacia sus clientes (CUSTOMER 07D.3A.1).

  `reply_to_email` = email OPERATIVO al que llegan las respuestas de los
  clientes a los emails que MiRubro envía en nombre del negocio (Reply-To).
  Es explícito: NO se deriva del email fiscal (`BusinessBillingProfile.email`),
  del owner ni de nadie; vacío = los emails salen sin Reply-To. El remitente
  (From) NO es configurable por el Business: es la identidad SES central.

  Comunicaciones automáticas (CUSTOMER 07D.4A): `appointment_email_enabled` /
  `no_show_email_enabled` deciden si, al vencer un `CustomerReminder`
  automático (`appointment_upcoming` / `no_show_followup`), se prepara además
  un `CustomerMessageDelivery` por email al cliente (ver
  `reminder_deliveries.py`). Arrancan APAGADOS para todo Business; solo email
  (sin lógica de canal preferido). El proveedor real lo decide el entorno
  (`CUSTOMER_DELIVERY_PROVIDER_EMAIL`), no este switch.

  Sin fila = defaults (sin Reply-To, todo apagado); la fila se crea en el primer PATCH.
  """

  business = models.OneToOneField(
    'business.Business', related_name='customer_communication_settings', on_delete=models.CASCADE,
  )
  reply_to_email = models.EmailField(blank=True, default='')
  # db_default: un writer viejo (sin estos campos) puede seguir insertando filas.
  appointment_email_enabled = models.BooleanField(default=False, db_default=False)
  no_show_email_enabled = models.BooleanField(default=False, db_default=False)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  @classmethod
  def for_business(cls, business) -> 'CustomerCommunicationSettings':
    """Fila del Business o una instancia NO guardada con los defaults."""
    existing = cls.objects.filter(business=business).first()
    return existing if existing is not None else cls(business=business)

  def __str__(self) -> str:
    return f"CustomerCommunication(business={self.business_id})"


class CustomerContactPreferences(models.Model):
  """Preferencias y consentimiento de contacto OPERATIVO del Customer (CUSTOMER 07D.1).

  Solo mensajes operativos (confirmar/recordar/reprogramar turno, seguimiento
  por inasistencia). NO cubre marketing: eso tendrá su propio consentimiento.
  Este modelo no envía nada; es la fuente que consultará la infraestructura
  de envío (07D.2) vía `contact_preferences.channel_status`.

  - Sin fila = defaults (WhatsApp/email apagados, sin canal preferido, sin
    opt-out). No se crea al leer ni al crear el Customer (ni por Turnos ni
    por reserva pública): reservar no es consentir. Se crea en el primer PATCH.
  - Llamadas (`phone_enabled`) es un canal MANUAL: nunca automático, por eso
    arranca permitido y no pide consentimiento.
  - WhatsApp/email: activarlos exige confirmar consentimiento Y un destino
    real (teléfono válido / email cargado); eso registra `*_consent_at`,
    `*_consent_source` y `*_consent_value` (el destino normalizado que se
    autorizó, CUSTOMER 07D.1.1). Si después cambia el teléfono/email del
    Customer, el canal deja de ser usable hasta reconfirmar. Apagarlos NO
    borra el registro (historial), pero un canal apagado nunca se usa.
  - `do_not_contact` gana sobre todo: con él activo ningún canal automático se
    ejecuta, sin tocar el resto de los flags.
  """

  class Channel(models.TextChoices):
    WHATSAPP = 'whatsapp', 'WhatsApp'
    EMAIL = 'email', 'Email'
    PHONE = 'phone', 'Llamada'

  class ConsentSource(models.TextChoices):
    MANUAL = 'manual', 'Registrado por el equipo'
    CUSTOMER_REQUEST = 'customer_request', 'Pedido del cliente'
    PUBLIC_BOOKING = 'public_booking', 'Reserva online'
    IMPORTED = 'imported', 'Importado'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='customer_contact_preferences', on_delete=models.CASCADE)
  customer = models.OneToOneField(Customer, related_name='contact_preferences', on_delete=models.CASCADE)
  whatsapp_enabled = models.BooleanField(default=False)
  email_enabled = models.BooleanField(default=False)
  phone_enabled = models.BooleanField(default=True)
  preferred_channel = models.CharField(max_length=16, choices=Channel.choices, null=True, blank=True)
  do_not_contact = models.BooleanField(default=False)
  whatsapp_consent_at = models.DateTimeField(null=True, blank=True)
  whatsapp_consent_source = models.CharField(max_length=32, choices=ConsentSource.choices, null=True, blank=True)
  # Destino autorizado (CUSTOMER 07D.1.1): dígitos E.164 del teléfono que el
  # cliente autorizó. NULL = no se sabe qué destino se autorizó (filas previas
  # a 07D.1.1) → el canal no es usable hasta reconfirmar.
  whatsapp_consent_value = models.CharField(max_length=32, null=True, blank=True)
  email_consent_at = models.DateTimeField(null=True, blank=True)
  email_consent_source = models.CharField(max_length=32, choices=ConsentSource.choices, null=True, blank=True)
  # Email autorizado, trim + lowercase. Misma regla que WhatsApp.
  email_consent_value = models.CharField(max_length=254, null=True, blank=True)
  updated_by = models.ForeignKey(
    settings.AUTH_USER_MODEL, related_name='+', on_delete=models.SET_NULL, null=True, blank=True,
  )
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    constraints = [
      # Un canal automático encendido siempre tiene un consentimiento registrado.
      models.CheckConstraint(
        check=Q(whatsapp_enabled=False) | (Q(whatsapp_consent_at__isnull=False) & Q(whatsapp_consent_source__isnull=False)),
        name='contact_prefs_whatsapp_requires_consent',
      ),
      models.CheckConstraint(
        check=Q(email_enabled=False) | (Q(email_consent_at__isnull=False) & Q(email_consent_source__isnull=False)),
        name='contact_prefs_email_requires_consent',
      ),
      # El canal preferido tiene que estar permitido.
      models.CheckConstraint(
        check=(
          Q(preferred_channel__isnull=True)
          | Q(preferred_channel='whatsapp', whatsapp_enabled=True)
          | Q(preferred_channel='email', email_enabled=True)
          | Q(preferred_channel='phone', phone_enabled=True)
        ),
        name='contact_prefs_preferred_channel_enabled',
      ),
    ]

  @classmethod
  def for_customer(cls, customer: Customer) -> 'CustomerContactPreferences':
    """Fila del Customer o una instancia NO guardada con los defaults."""
    existing = cls.objects.filter(customer=customer).first()
    return existing if existing is not None else cls(customer=customer, business_id=customer.business_id)

  def is_channel_enabled(self, channel: str) -> bool:
    return bool(getattr(self, f'{channel}_enabled'))

  def save(self, *args, **kwargs):
    # Tenant safety, mismo criterio que notas/recordatorios.
    if self.customer_id is not None:
      customer_business_id = self.customer.business_id
      if self.business_id is None:
        self.business_id = customer_business_id
      elif self.business_id != customer_business_id:
        raise ValueError('CustomerContactPreferences.business must match customer.business.')
    super().save(*args, **kwargs)

  def __str__(self) -> str:
    return f"ContactPreferences({self.customer_id})"


class CustomerMessageDelivery(models.Model):
  """UN intento lógico de comunicación externa a un Customer (CUSTOMER 07D.2).

  Infraestructura de envío: todavía NO hay proveedor real (solo fakes sin
  network, ver `delivery_providers.py`). El ciclo de vida lo administran
  `deliveries.prepare_customer_delivery` / `execute_delivery`; nada lo muta
  desde la API (solo lectura para auditoría en la ficha).

  - `destination_snapshot`: destino EXACTO (WhatsApp dígitos E.164 / email
    normalizado) resuelto al preparar. Nunca se reconstruye leyendo el
    Customer; si al ejecutar el destino usable actual es otro → `skipped`
    (`destination_changed`), nunca se reescribe a otro destino.
  - `idempotency_key` única por Business: reprocesar el mismo evento devuelve
    el mismo Delivery.
  - `skipped` = decisión de negocio (opt-out, canal apagado, consentimiento,
    destino); `failed` = error técnico del proveedor. `sent` = el proveedor
    lo aceptó; `delivered` solo si el proveedor confirma la entrega.
  - `failed` con `next_retry_at` = reintento programado; sin él = final.
  - NO es `CustomerReminder.notified_at` (aviso interno del 07C).
  - Sin secretos ni el mensaje renderizado: `context` guarda ids y snapshots
    mínimos para un render futuro.
  """

  FAILURE_MESSAGE_MAX_LENGTH = 500

  class Channel(models.TextChoices):
    WHATSAPP = 'whatsapp', 'WhatsApp'
    EMAIL = 'email', 'Email'

  class Purpose(models.TextChoices):
    APPOINTMENT_REMINDER = 'appointment_reminder', 'Recordatorio de turno'
    NO_SHOW_FOLLOWUP = 'no_show_followup', 'Seguimiento por inasistencia'

  class TemplateKey(models.TextChoices):
    APPOINTMENT_REMINDER_V1 = 'appointment_reminder_v1', 'Recordatorio de turno v1'
    NO_SHOW_FOLLOWUP_V1 = 'no_show_followup_v1', 'Seguimiento por inasistencia v1'

  class Status(models.TextChoices):
    PENDING = 'pending', 'Pendiente'
    PROCESSING = 'processing', 'Enviando'
    SENT = 'sent', 'Enviado'
    DELIVERED = 'delivered', 'Entregado'
    FAILED = 'failed', 'Fallido'
    SKIPPED = 'skipped', 'Omitido'
    CANCELLED = 'cancelled', 'Cancelado'

  class Provider(models.TextChoices):
    FAKE_WHATSAPP = 'fake_whatsapp', 'Fake WhatsApp (sin envío)'
    FAKE_EMAIL = 'fake_email', 'Fake Email (sin envío)'
    SES = 'ses', 'Amazon SES'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='customer_message_deliveries', on_delete=models.CASCADE)
  customer = models.ForeignKey(Customer, related_name='message_deliveries', on_delete=models.CASCADE)
  # El historial queda aunque se borre el turno/recordatorio que lo originó.
  appointment = models.ForeignKey(
    'appointments.Appointment', related_name='customer_message_deliveries', on_delete=models.SET_NULL, null=True, blank=True,
  )
  # FK (no OneToOne): un recordatorio puede producir 0..N deliveries (uno por
  # canal); los duplicados los controla `idempotency_key`.
  reminder = models.ForeignKey(
    CustomerReminder, related_name='message_deliveries', on_delete=models.SET_NULL, null=True, blank=True,
  )
  channel = models.CharField(max_length=16, choices=Channel.choices)
  purpose = models.CharField(max_length=32, choices=Purpose.choices)
  template_key = models.CharField(max_length=64, choices=TemplateKey.choices, null=True, blank=True)
  destination_snapshot = models.CharField(max_length=254, null=True, blank=True)
  status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
  provider = models.CharField(max_length=32, choices=Provider.choices, null=True, blank=True)
  provider_message_id = models.CharField(max_length=255, null=True, blank=True)
  idempotency_key = models.CharField(max_length=200)
  context = models.JSONField(default=dict, blank=True)
  attempt_count = models.PositiveSmallIntegerField(default=0)
  last_attempt_at = models.DateTimeField(null=True, blank=True)
  next_retry_at = models.DateTimeField(null=True, blank=True)
  sent_at = models.DateTimeField(null=True, blank=True)
  delivered_at = models.DateTimeField(null=True, blank=True)
  failed_at = models.DateTimeField(null=True, blank=True)
  skipped_at = models.DateTimeField(null=True, blank=True)
  cancelled_at = models.DateTimeField(null=True, blank=True)
  # Motivo de negocio de un `skipped` (códigos de `contact_preferences` +
  # `destination_changed` / `customer_inactive`). Nunca es un error técnico.
  skip_reason = models.CharField(max_length=64, null=True, blank=True)
  # Error técnico del proveedor (`failed`). `failure_message` es interno
  # (puede traer detalle del proveedor): la API no lo expone.
  failure_code = models.CharField(max_length=64, null=True, blank=True)
  failure_message = models.CharField(max_length=FAILURE_MESSAGE_MAX_LENGTH, null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['-created_at', '-id']
    indexes = [
      models.Index(fields=['business', 'customer', '-created_at'], name='customer_delivery_feed_idx'),
      # Barrido de Beat: reintentos vencidos.
      models.Index(
        fields=['next_retry_at'],
        condition=Q(status='failed', next_retry_at__isnull=False),
        name='customer_delivery_retry_idx',
      ),
      # Barrido de Beat: pendientes cuyo encolado se perdió / processing colgados.
      models.Index(
        fields=['status', 'created_at'],
        condition=Q(status__in=['pending', 'processing']),
        name='customer_delivery_open_idx',
      ),
    ]
    constraints = [
      models.UniqueConstraint(fields=['business', 'idempotency_key'], name='customer_delivery_unique_idempotency_key'),
      models.CheckConstraint(check=~Q(idempotency_key=''), name='customer_delivery_idempotency_key_not_empty'),
      # Todo lo que puede llegar (o llegó) al proveedor tiene destino congelado.
      models.CheckConstraint(
        check=Q(status__in=['skipped', 'cancelled']) | (Q(destination_snapshot__isnull=False) & ~Q(destination_snapshot='')),
        name='customer_delivery_destination_required',
      ),
      models.CheckConstraint(
        check=(Q(status='skipped') & Q(skip_reason__isnull=False) & Q(skipped_at__isnull=False))
        | (~Q(status='skipped') & Q(skip_reason__isnull=True)),
        name='customer_delivery_skip_reason_matches_status',
      ),
      models.CheckConstraint(
        check=~Q(status='failed') | (Q(failure_code__isnull=False) & Q(failed_at__isnull=False)),
        name='customer_delivery_failed_has_code',
      ),
      models.CheckConstraint(
        check=~Q(status__in=['sent', 'delivered']) | Q(sent_at__isnull=False),
        name='customer_delivery_sent_has_sent_at',
      ),
      models.CheckConstraint(
        check=Q(next_retry_at__isnull=True) | Q(status='failed'),
        name='customer_delivery_retry_only_when_failed',
      ),
    ]

  def save(self, *args, **kwargs):
    # Tenant safety, mismo criterio que notas/recordatorios: nunca un Customer,
    # turno o recordatorio de otro Business.
    if self.customer_id is not None:
      customer_business_id = self.customer.business_id
      if self.business_id is None:
        self.business_id = customer_business_id
      elif self.business_id != customer_business_id:
        raise ValueError('CustomerMessageDelivery.business must match customer.business.')
      if self.appointment_id is not None and self.appointment.business_id != customer_business_id:
        raise ValueError('CustomerMessageDelivery.appointment must belong to the same business.')
      if self.reminder_id is not None and (
        self.reminder.business_id != customer_business_id or self.reminder.customer_id != self.customer_id
      ):
        raise ValueError('CustomerMessageDelivery.reminder must belong to the same customer.')
    super().save(*args, **kwargs)

  def __str__(self) -> str:
    return f"Delivery {self.pk} ({self.channel}/{self.purpose}, {self.status})"
