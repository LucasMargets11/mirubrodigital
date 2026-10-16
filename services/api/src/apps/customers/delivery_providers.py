"""Abstracción de proveedores de envío al Customer (CUSTOMER 07D.2).

El negocio (`deliveries.py`) solo conoce `DeliveryProvider.send(message)` y un
`ProviderSendResult` normalizado; nunca Meta/SES/SendGrid ni sus estados.

Proveedores:
- Fake (WhatsApp/Email): sin network. Default en todo entorno.
- `AmazonSESProvider` (07D.3A, email): cuenta SES central de MiRubro, nunca
  credenciales por Business. Solo se usa con opt-in explícito
  `CUSTOMER_DELIVERY_PROVIDER_EMAIL=ses` (o `--provider ses` en el comando de
  QA); sin eso, email = fake. No hay autodetección por credenciales/entorno.

Contrato para cualquier proveedor:
- Devolver `ProviderSendResult` para todo resultado CONOCIDO (aceptado,
  rechazo definitivo, error transitorio en el que es seguro reintentar).
- Una excepción significa "resultado desconocido" (p. ej. timeout después de
  haber enviado el request): el Delivery queda `failed` SIN reintento, para no
  mandar dos veces el mismo mensaje al cliente (at-most-once).
- Nunca incluir credenciales en `error_message`.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from email.utils import formataddr, parseaddr

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .models import CustomerMessageDelivery

logger = logging.getLogger(__name__)

Channel = CustomerMessageDelivery.Channel
Provider = CustomerMessageDelivery.Provider


@dataclass(frozen=True)
class DeliveryMessage:
  """Lo que recibe el proveedor: datos planos, nunca el ORM."""
  delivery_id: str
  business_id: str
  channel: str
  purpose: str
  destination: str
  idempotency_key: str
  template_key: str | None = None
  context: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderSendResult:
  accepted: bool
  provider_message_id: str | None = None
  retryable: bool = False
  error_code: str | None = None
  error_message: str | None = None

  @classmethod
  def ok(cls, provider_message_id: str) -> 'ProviderSendResult':
    return cls(accepted=True, provider_message_id=provider_message_id)

  @classmethod
  def failure(cls, error_code: str, error_message: str = '', *, retryable: bool) -> 'ProviderSendResult':
    return cls(accepted=False, retryable=retryable, error_code=error_code, error_message=error_message or None)


class DeliveryProvider:
  name: str = 'base'
  channel: str = ''

  def send(self, message: DeliveryMessage) -> ProviderSendResult:
    raise NotImplementedError


class FakeProvider(DeliveryProvider):
  """Proveedor de desarrollo/QA: no hace network ni manda nada.

  `mode`:
  - `success`: acepta y devuelve `fake-<uuid>`.
  - `retryable_failure`: error transitorio (`fake_temporary_error`).
  - `permanent_failure`: rechazo definitivo (`fake_rejected`).
  Default: `settings.CUSTOMER_DELIVERY_FAKE_MODE` (success). Los tests
  inyectan una instancia con el modo que necesitan.
  """
  MODES = ('success', 'retryable_failure', 'permanent_failure')

  def __init__(self, mode: str | None = None):
    mode = mode or getattr(settings, 'CUSTOMER_DELIVERY_FAKE_MODE', 'success') or 'success'
    if mode not in self.MODES:
      raise ValueError(f'Unknown fake delivery mode: {mode}')
    self.mode = mode
    self.sent: list[DeliveryMessage] = []

  def send(self, message: DeliveryMessage) -> ProviderSendResult:
    self.sent.append(message)
    if self.mode == 'retryable_failure':
      return ProviderSendResult.failure('fake_temporary_error', 'Fake provider: error transitorio simulado', retryable=True)
    if self.mode == 'permanent_failure':
      return ProviderSendResult.failure('fake_rejected', 'Fake provider: rechazo definitivo simulado', retryable=False)
    return ProviderSendResult.ok(f'fake-{uuid.uuid4().hex}')


class FakeWhatsAppProvider(FakeProvider):
  name = Provider.FAKE_WHATSAPP
  channel = Channel.WHATSAPP


class FakeEmailProvider(FakeProvider):
  name = Provider.FAKE_EMAIL
  channel = Channel.EMAIL


class ProviderOutcomeUnknown(Exception):
  """El request pudo haber llegado al proveedor pero no sabemos el resultado
  (timeout de lectura, conexión cortada). Se propaga como excepción para que
  `execute_delivery` aplique la política at-most-once (failed, sin reintento)."""


# ── Amazon SES (v2) ──────────────────────────────────────────────────────────

# Códigos de error de SES v2 / AWS. Un ClientError significa que AWS respondió
# y NO aceptó el mensaje: nunca es "resultado desconocido".
_SES_THROTTLE_CODES = frozenset({
  'TooManyRequestsException', 'Throttling', 'ThrottlingException', 'LimitExceededException',
})
_SES_UNAVAILABLE_CODES = frozenset({
  'ServiceUnavailable', 'ServiceUnavailableException', 'InternalFailure', 'InternalServiceError',
  'InternalServerError', 'RequestTimeout', 'RequestTimeoutException',
})
_SES_CONFIG_CODES = frozenset({
  'MailFromDomainNotVerifiedException', 'NotFoundException', 'AccessDenied', 'AccessDeniedException',
  'UnrecognizedClientException', 'InvalidClientTokenId', 'SignatureDoesNotMatch', 'ExpiredToken',
  'ExpiredTokenException', 'InvalidSignatureException', 'MissingAuthenticationToken',
})
_SES_ACCOUNT_CODES = frozenset({'AccountSuspendedException', 'SendingPausedException'})
_SES_BAD_REQUEST_CODES = frozenset({'BadRequestException', 'ValidationException', 'InvalidParameterValue'})
_SES_TAG_SAFE = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-')

DEFAULT_PLATFORM_NAME = 'MiRubro'
BUSINESS_NAME_MAX_LENGTH = 64


def _tag_value(value) -> str:
  return ''.join(ch if ch in _SES_TAG_SAFE else '_' for ch in str(value or ''))[:256] or 'none'


def _valid_email(value) -> str | None:
  value = (value or '').strip()
  try:
    validate_email(value)
  except ValidationError:
    return None
  return value


def ses_sender() -> tuple[str, str]:
  """(nombre de plataforma, dirección verificada). La dirección sale SOLO de
  settings (`AWS_SES_FROM_EMAIL`, o la de `DEFAULT_FROM_EMAIL`); nunca de la DB."""
  default_name, default_address = parseaddr(getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '')
  address = (getattr(settings, 'AWS_SES_FROM_EMAIL', '') or '').strip() or default_address
  name = (getattr(settings, 'AWS_SES_FROM_NAME', '') or '').strip() or default_name or DEFAULT_PLATFORM_NAME
  return name, address


def ses_from_header(business_name: str | None) -> str:
  """'Pinturería Chascomús vía MiRubro <notificaciones@…>' (RFC 2047 si hace falta).
  El Business solo personaliza el display name; la dirección es la identidad central."""
  platform, address = ses_sender()
  business_name = ' '.join(str(business_name or '').split())[:BUSINESS_NAME_MAX_LENGTH].strip()
  display = f'{business_name} vía {platform}' if business_name else platform
  return formataddr((display, address), charset='utf-8')


class AmazonSESProvider(DeliveryProvider):
  """Email transaccional vía SES v2 (`sesv2.send_email`), cuenta central MiRubro.

  - Credenciales: cadena normal de boto3 (IAM/task role, env, profile local);
    misma región/config set que `apps.notifications` (`AWS_SES_REGION`,
    `AWS_SES_CONFIGURATION_SET`). Nada se guarda en DB.
  - Reintentos internos de botocore DESACTIVADOS (`total_max_attempts=1`): un
    reintento automático tras un timeout de lectura podría mandar dos veces.
    Los reintentos los decide `deliveries.py` según `ProviderSendResult`.
  - `accepted` = SES aceptó (MessageId). NO es entregado (eso vendrá por eventos).
  - Template/contexto inválido → fallo definitivo sin llamar a SES.
  - Nunca se guarda ni loguea el mensaje crudo de AWS (puede traer el email
    del destinatario): solo código propio + código AWS + RequestId.
  """
  name = Provider.SES
  channel = Channel.EMAIL

  CONNECT_TIMEOUT_SECONDS = 5
  READ_TIMEOUT_SECONDS = 20

  def __init__(self, client=None):
    self._client = client

  def _get_client(self):
    if self._client is None:
      import boto3
      from botocore.config import Config

      self._client = boto3.client(
        'sesv2',
        region_name=settings.AWS_SES_REGION,
        config=Config(
          retries={'total_max_attempts': 1, 'mode': 'standard'},
          connect_timeout=self.CONNECT_TIMEOUT_SECONDS,
          read_timeout=self.READ_TIMEOUT_SECONDS,
        ),
      )
    return self._client

  def build_payload(self, message: DeliveryMessage) -> dict:
    from .delivery_templates import render_email

    rendered = render_email(message.template_key, message.context)
    payload = {
      'FromEmailAddress': ses_from_header(message.context.get('business_name')),
      'Destination': {'ToAddresses': [message.destination]},
      'Content': {
        'Simple': {
          'Subject': {'Data': rendered.subject, 'Charset': 'UTF-8'},
          'Body': {
            'Text': {'Data': rendered.text_body, 'Charset': 'UTF-8'},
            'Html': {'Data': rendered.html_body, 'Charset': 'UTF-8'},
          },
        },
      },
      # Solo ids/no PII: correlación de eventos SES (07D.3B).
      'EmailTags': [
        {'Name': 'delivery_id', 'Value': _tag_value(message.delivery_id)},
        {'Name': 'business_id', 'Value': _tag_value(message.business_id)},
        {'Name': 'purpose', 'Value': _tag_value(message.purpose)},
        {'Name': 'template', 'Value': _tag_value(message.template_key)},
      ],
    }
    reply_to = _valid_email(message.context.get('business_reply_to'))
    if reply_to:
      payload['ReplyToAddresses'] = [reply_to]
    configuration_set = (getattr(settings, 'AWS_SES_CONFIGURATION_SET', '') or '').strip()
    if configuration_set:
      payload['ConfigurationSetName'] = configuration_set
    return payload

  def send(self, message: DeliveryMessage) -> ProviderSendResult:
    from botocore.exceptions import (
      BotoCoreError, ClientError, ConnectTimeoutError, EndpointConnectionError, NoCredentialsError,
      NoRegionError, PartialCredentialsError,
    )

    from .delivery_templates import TemplateRenderError

    if message.channel != Channel.EMAIL:
      return self._fail(message, 'ses_unsupported_channel', 'SES solo envía email', retryable=False)
    if not _valid_email(message.destination):
      return self._fail(message, 'ses_invalid_destination', 'Destino de email inválido', retryable=False)
    if not _valid_email(ses_sender()[1]):
      return self._fail(message, 'ses_sender_not_configured', 'AWS_SES_FROM_EMAIL/DEFAULT_FROM_EMAIL inválido', retryable=False)
    try:
      payload = self.build_payload(message)
    except TemplateRenderError as exc:
      return self._fail(message, exc.code, str(exc), retryable=False)

    try:
      response = self._get_client().send_email(**payload)
    except ClientError as exc:
      return self._client_error(message, exc)
    except (NoCredentialsError, PartialCredentialsError):
      return self._fail(message, 'ses_credentials_missing', 'Sin credenciales AWS en la cadena de boto3', retryable=False)
    except NoRegionError:
      return self._fail(message, 'ses_configuration_error', 'AWS_SES_REGION no configurada', retryable=False)
    except (EndpointConnectionError, ConnectTimeoutError):
      # No llegó a conectarse: el request no salió → seguro reintentar.
      return self._fail(message, 'ses_network_error', 'No se pudo conectar con SES', retryable=True)
    except BotoCoreError as exc:
      # Timeout de lectura / conexión cortada / otros: SES pudo haberlo aceptado.
      logger.error('[CustomerDelivery] ses outcome unknown delivery=%s business=%s provider=ses error=%s',
                   message.delivery_id, message.business_id, type(exc).__name__)
      raise ProviderOutcomeUnknown(type(exc).__name__) from exc

    message_id = (response or {}).get('MessageId')
    if not message_id:
      # Respuesta sin MessageId: no sabemos si quedó encolado → no reintentar a ciegas.
      raise ProviderOutcomeUnknown('SES response without MessageId')
    logger.info('[CustomerDelivery] ses accepted delivery=%s business=%s provider=ses request_id=%s',
                message.delivery_id, message.business_id, (response.get('ResponseMetadata') or {}).get('RequestId', '-'))
    return ProviderSendResult.ok(message_id)

  def _client_error(self, message: DeliveryMessage, exc) -> ProviderSendResult:
    error = exc.response.get('Error') or {}
    metadata = exc.response.get('ResponseMetadata') or {}
    code = str(error.get('Code') or 'Unknown')
    http_status = int(metadata.get('HTTPStatusCode') or 0)
    suffix = f' (AWS {code}, request {metadata.get("RequestId", "-")})'

    def fail(our_code, text, retryable):
      return self._fail(message, our_code, text + suffix, retryable=retryable, aws_code=code)

    if code in _SES_THROTTLE_CODES:
      return fail('ses_throttled', 'SES limitó la tasa de envío', True)
    if code in _SES_UNAVAILABLE_CODES:
      return fail('ses_unavailable', 'Error transitorio de SES', True)
    if code == 'MessageRejected':
      # SES no expone un código distinto para "no verificado": se mira el texto,
      # pero el texto crudo (trae el email) nunca se persiste.
      if 'not verified' in str(error.get('Message') or '').lower():
        return fail('ses_identity_not_verified',
                    'SES rechazó: identidad no verificada (¿cuenta en sandbox? verificar remitente y destinatario)', False)
      return fail('ses_message_rejected', 'SES rechazó el mensaje', False)
    if code in _SES_CONFIG_CODES:
      return fail('ses_configuration_error', 'Configuración o permisos de SES inválidos', False)
    if code in _SES_ACCOUNT_CODES:
      return fail('ses_account_paused', 'Envío pausado o suspendido en la cuenta SES', False)
    if code in _SES_BAD_REQUEST_CODES:
      return fail('ses_bad_request', 'SES rechazó el request (parámetro inválido)', False)
    if http_status >= 500:
      return fail('ses_unavailable', 'Error transitorio de SES', True)
    return fail('ses_error', 'Error de SES', False)

  def _fail(self, message: DeliveryMessage, code: str, text: str, *, retryable: bool, aws_code: str = '-') -> ProviderSendResult:
    logger.warning('[CustomerDelivery] ses failed delivery=%s business=%s provider=ses code=%s aws_code=%s retryable=%s',
                   message.delivery_id, message.business_id, code, aws_code, retryable)
    return ProviderSendResult.failure(code, text, retryable=retryable)


_FAKE_BY_CHANNEL = {Channel.WHATSAPP: FakeWhatsAppProvider, Channel.EMAIL: FakeEmailProvider}

PROVIDER_NAMES_BY_CHANNEL = {Channel.WHATSAPP: ('fake',), Channel.EMAIL: ('fake', 'ses')}


def get_provider(channel: str, name: str | None = None) -> DeliveryProvider:
  """Proveedor activo para el canal.

  `name` (fake|ses) fuerza uno; si no, email usa `CUSTOMER_DELIVERY_PROVIDER_EMAIL`
  (default fake) y WhatsApp siempre fake. Un valor desconocido es error: nunca
  se cae silenciosamente a otro proveedor.
  """
  if channel not in _FAKE_BY_CHANNEL:
    raise ValueError(f'No delivery provider for channel: {channel}')
  if name is None and channel == Channel.EMAIL:
    name = getattr(settings, 'CUSTOMER_DELIVERY_PROVIDER_EMAIL', 'fake')
  name = (name or 'fake').strip().lower()
  if name not in PROVIDER_NAMES_BY_CHANNEL[channel]:
    raise ValueError(f'Unsupported delivery provider {name!r} for channel {channel}')
  if name == 'ses':
    return AmazonSESProvider()
  return _FAKE_BY_CHANNEL[channel]()
