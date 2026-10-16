"""Amazon SES real para CustomerMessageDelivery (CUSTOMER 07D.3A).

boto3 SIEMPRE mockeado: se inyecta un cliente falso en `AmazonSESProvider`, y
`boto3.client` está parcheado para fallar si algún camino intentara crear uno
real. Nada sale a la red.
"""
from __future__ import annotations

import datetime as dt
from io import StringIO
from unittest.mock import MagicMock, patch

from botocore.exceptions import (
  ClientError, ConnectTimeoutError, EndpointConnectionError, NoCredentialsError, ReadTimeoutError,
)
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone as dj_timezone

from apps.appointments.tests.test_customer_core_access import _turnos_business

from .deliveries import execute_delivery, retry_due_customer_deliveries
from .delivery_providers import (
  AmazonSESProvider, DeliveryMessage, FakeEmailProvider, ProviderOutcomeUnknown, get_provider, ses_from_header,
)
from .delivery_templates import TemplateRenderError, render_email
from .models import CustomerCommunicationSettings, CustomerMessageDelivery
from .test_deliveries import EMAIL, DeliveryMixin

D = CustomerMessageDelivery
S = D.Status
TEMPLATE = D.TemplateKey.APPOINTMENT_REMINDER_V1

SES_SETTINGS = dict(
  AWS_SES_REGION='sa-east-1', AWS_SES_FROM_EMAIL='notificaciones@mirubro.com.ar', AWS_SES_FROM_NAME='MiRubro',
  AWS_SES_CONFIGURATION_SET='',
)


def _client_error(code, message='boom', status=400):
  return ClientError(
    {'Error': {'Code': code, 'Message': message}, 'ResponseMetadata': {'RequestId': 'req-1', 'HTTPStatusCode': status}},
    'SendEmail',
  )


def _ses_client(message_id='0100-ses-message-id'):
  client = MagicMock()
  client.send_email.return_value = {'MessageId': message_id, 'ResponseMetadata': {'RequestId': 'req-ok'}}
  return client


def _context(**overrides):
  context = {
    'customer_name': 'Ana Pérez',
    'business_name': 'Pinturería Chascomús',
    'business_timezone': 'America/Argentina/Buenos_Aires',
    # 2026-10-06 17:30 UTC = martes 6, 14:30 en Buenos Aires (UTC-3).
    'appointment_start_at': '2026-10-06T17:30:00+00:00',
    'service_name': 'Corte',
    'business_reply_to': None,
  }
  context.update(overrides)
  return context


def _message(**overrides):
  fields = dict(
    delivery_id='11111111-1111-1111-1111-111111111111', business_id='22222222-2222-2222-2222-222222222222',
    channel=EMAIL, purpose=D.Purpose.APPOINTMENT_REMINDER, destination='cliente@example.com',
    idempotency_key='k', template_key=TEMPLATE, context=_context(),
  )
  fields.update(overrides)
  return DeliveryMessage(**fields)


# ── Templates (23-28) ────────────────────────────────────────────────────────

class AppointmentReminderTemplateTests(SimpleTestCase):

  def test_23_subject(self):
    self.assertEqual(render_email(TEMPLATE, _context()).subject, 'Recordatorio de turno - Pinturería Chascomús')

  def test_24_date_and_time_in_business_timezone(self):
    rendered = render_email(TEMPLATE, _context())
    self.assertIn('Fecha: martes 6 de octubre de 2026', rendered.text_body)
    self.assertIn('Hora: 14:30 hs', rendered.text_body)
    self.assertIn('14:30 hs', rendered.html_body)
    # Otro Business timezone → otra hora local para el mismo instante.
    madrid = render_email(TEMPLATE, _context(business_timezone='Europe/Madrid'))
    self.assertIn('Hora: 19:30 hs', madrid.text_body)

  def test_24b_date_can_shift_day_by_timezone(self):
    rendered = render_email(TEMPLATE, _context(appointment_start_at='2026-10-07T01:30:00+00:00'))
    self.assertIn('martes 6 de octubre de 2026', rendered.text_body)
    self.assertIn('22:30 hs', rendered.text_body)

  def test_25_service_is_optional(self):
    for value in (None, ''):
      with self.subTest(service=value):
        rendered = render_email(TEMPLATE, _context(service_name=value))
        self.assertNotIn('Servicio', rendered.text_body)
        self.assertNotIn('Servicio', rendered.html_body)
    self.assertIn('Servicio: Corte', render_email(TEMPLATE, _context()).text_body)

  def test_26_html_is_escaped(self):
    rendered = render_email(TEMPLATE, _context(
      customer_name='<script>alert(1)</script>', business_name='A & B "Shop"', service_name='<b>x</b>',
    ))
    self.assertNotIn('<script>', rendered.html_body)
    self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', rendered.html_body)
    self.assertIn('A &amp; B &quot;Shop&quot;', rendered.html_body)
    self.assertIn('&lt;b&gt;x&lt;/b&gt;', rendered.html_body)
    # El texto plano no se escapa (no es HTML).
    self.assertIn('Hola <script>alert(1)</script>,', rendered.text_body)

  def test_27_text_fallback_has_full_content(self):
    text = render_email(TEMPLATE, _context()).text_body
    for fragment in ('Hola Ana Pérez,', 'Te recordamos tu turno en Pinturería Chascomús.',
                     'Si necesitás modificar tu turno, comunicate con el negocio.',
                     'MiRubro actúa como plataforma tecnológica.'):
      self.assertIn(fragment, text)
    self.assertNotIn('<', text)

  def test_28_incomplete_context_is_controlled_error(self):
    for key in ('customer_name', 'business_name', 'appointment_start_at', 'business_timezone'):
      with self.subTest(missing=key), self.assertRaises(TemplateRenderError) as ctx:
        render_email(TEMPLATE, _context(**{key: None}))
      self.assertEqual(ctx.exception.code, 'template_context_invalid')
    for bad in ('mañana', '2026-10-06T17:30:00'):  # inválido / naive
      with self.subTest(start=bad), self.assertRaises(TemplateRenderError):
        render_email(TEMPLATE, _context(appointment_start_at=bad))
    for unsupported in (None, '', 'whatsapp_v1'):  # no_show_followup_v1 existe desde 07D.4A
      with self.subTest(template=unsupported), self.assertRaises(TemplateRenderError) as ctx:
        render_email(unsupported, _context())
      self.assertEqual(ctx.exception.code, 'template_unsupported')

  def test_subject_has_no_newlines(self):
    rendered = render_email(TEMPLATE, _context(business_name='Biz\r\nBcc: x@y.com'))
    self.assertNotIn('\n', rendered.subject)
    self.assertNotIn('\r', rendered.subject)


# ── Provider unitario (1-11) ─────────────────────────────────────────────────

@override_settings(**SES_SETTINGS)
@patch('boto3.client', side_effect=AssertionError('real boto3 client must not be created in tests'))
class AmazonSESProviderTests(SimpleTestCase):

  def _send(self, client, **overrides):
    return AmazonSESProvider(client=client).send(_message(**overrides))

  def test_1_success_returns_message_id(self, _boto):
    result = self._send(_ses_client('abc-123'))
    self.assertTrue(result.accepted)
    self.assertEqual(result.provider_message_id, 'abc-123')

  def test_2_3_4_from_to_subject_bodies(self, _boto):
    client = _ses_client()
    self._send(client)
    payload = client.send_email.call_args.kwargs
    self.assertIn('<notificaciones@mirubro.com.ar>', payload['FromEmailAddress'])
    self.assertEqual(payload['FromEmailAddress'], ses_from_header('Pinturería Chascomús'))
    self.assertEqual(payload['Destination'], {'ToAddresses': ['cliente@example.com']})
    simple = payload['Content']['Simple']
    self.assertEqual(simple['Subject']['Data'], 'Recordatorio de turno - Pinturería Chascomús')
    self.assertIn('Hora: 14:30 hs', simple['Body']['Text']['Data'])
    self.assertIn('<strong>Pinturería Chascomús</strong>', simple['Body']['Html']['Data'])
    self.assertNotIn('ReplyToAddresses', payload)
    self.assertNotIn('Cc', str(payload['Destination']))

  def test_2b_from_display_name_is_business_via_mirubro(self, _boto):
    from email.header import decode_header, make_header
    from email.utils import parseaddr

    name, address = parseaddr(str(make_header(decode_header(ses_from_header('Pinturería Chascomús')))))
    self.assertEqual((name, address), ('Pinturería Chascomús vía MiRubro', 'notificaciones@mirubro.com.ar'))
    # Sin nombre de Business → solo la plataforma. Un nombre no inyecta direcciones.
    self.assertEqual(parseaddr(ses_from_header(''))[1], 'notificaciones@mirubro.com.ar')
    self.assertEqual(parseaddr(ses_from_header('Evil <x@evil.com>'))[1], 'notificaciones@mirubro.com.ar')

  def test_reply_to_only_with_valid_business_email(self, _boto):
    client = _ses_client()
    self._send(client, context=_context(business_reply_to='hola@negocio.com'))
    self.assertEqual(client.send_email.call_args.kwargs['ReplyToAddresses'], ['hola@negocio.com'])
    client = _ses_client()
    self._send(client, context=_context(business_reply_to='no-es-email'))
    self.assertNotIn('ReplyToAddresses', client.send_email.call_args.kwargs)

  def test_5_configuration_set_optional(self, _boto):
    client = _ses_client()
    self._send(client)
    self.assertNotIn('ConfigurationSetName', client.send_email.call_args.kwargs)
    with override_settings(AWS_SES_CONFIGURATION_SET='mirubro-customer'):
      client = _ses_client()
      self._send(client)
    self.assertEqual(client.send_email.call_args.kwargs['ConfigurationSetName'], 'mirubro-customer')

  def test_6_tags_are_ids_only(self, _boto):
    client = _ses_client()
    self._send(client)
    tags = {t['Name']: t['Value'] for t in client.send_email.call_args.kwargs['EmailTags']}
    self.assertEqual(tags, {
      'delivery_id': '11111111-1111-1111-1111-111111111111', 'business_id': '22222222-2222-2222-2222-222222222222',
      'purpose': 'appointment_reminder', 'template': 'appointment_reminder_v1',
    })
    flat = str(tags)
    for pii in ('cliente@example.com', 'Ana', 'Pinturería'):
      self.assertNotIn(pii, flat)

  def test_7_retryable_aws_errors(self, _boto):
    for code, status, expected in (
      ('TooManyRequestsException', 429, 'ses_throttled'), ('Throttling', 400, 'ses_throttled'),
      ('ServiceUnavailable', 503, 'ses_unavailable'), ('InternalFailure', 500, 'ses_unavailable'),
      ('SomethingNew', 502, 'ses_unavailable'),
    ):
      with self.subTest(code=code):
        client = MagicMock()
        client.send_email.side_effect = _client_error(code, status=status)
        result = self._send(client)
        self.assertFalse(result.accepted)
        self.assertTrue(result.retryable)
        self.assertEqual(result.error_code, expected)
    client = MagicMock()
    client.send_email.side_effect = EndpointConnectionError(endpoint_url='https://email.sa-east-1.amazonaws.com')
    result = self._send(client)
    self.assertEqual((result.error_code, result.retryable), ('ses_network_error', True))

  def test_8_permanent_rejections(self, _boto):
    for code, message, expected in (
      ('MessageRejected', 'Email address is not verified. The following identities failed the check in region SA-EAST-1: cliente@example.com',
       'ses_identity_not_verified'),
      ('MessageRejected', 'Illegal address', 'ses_message_rejected'),
      ('MailFromDomainNotVerifiedException', 'x', 'ses_configuration_error'),
      ('NotFoundException', 'Configuration set does not exist', 'ses_configuration_error'),
      ('AccessDeniedException', 'not authorized', 'ses_configuration_error'),
      ('AccountSuspendedException', 'x', 'ses_account_paused'),
      ('BadRequestException', 'x', 'ses_bad_request'),
      ('WhoKnows', 'x', 'ses_error'),
    ):
      with self.subTest(code=code, expected=expected):
        client = MagicMock()
        client.send_email.side_effect = _client_error(code, message)
        result = self._send(client)
        self.assertFalse(result.accepted)
        self.assertFalse(result.retryable)
        self.assertEqual(result.error_code, expected)
        # Nunca el mensaje crudo de AWS (puede traer el email).
        self.assertNotIn('cliente@example.com', result.error_message)
        self.assertIn(code, result.error_message)
        self.assertIn('req-1', result.error_message)

  def test_9_timeout_is_outcome_unknown(self, _boto):
    client = MagicMock()
    client.send_email.side_effect = ReadTimeoutError(endpoint_url='https://email.sa-east-1.amazonaws.com')
    with self.assertRaises(ProviderOutcomeUnknown):
      self._send(client)
    # Connect timeout: el request nunca salió → reintentable, no desconocido.
    client = MagicMock()
    client.send_email.side_effect = ConnectTimeoutError(endpoint_url='https://email.sa-east-1.amazonaws.com')
    self.assertEqual(self._send(client).error_code, 'ses_network_error')
    # 200 sin MessageId → desconocido.
    client = MagicMock()
    client.send_email.return_value = {}
    with self.assertRaises(ProviderOutcomeUnknown):
      self._send(client)

  def test_10_no_credentials(self, _boto):
    client = MagicMock()
    client.send_email.side_effect = NoCredentialsError()
    result = self._send(client)
    self.assertEqual((result.accepted, result.retryable, result.error_code), (False, False, 'ses_credentials_missing'))

  def test_11_no_real_network_and_botocore_retries_disabled(self, boto_client):
    # Sin cliente inyectado se construye con boto3.client (parcheado → no red).
    provider = AmazonSESProvider()
    with self.assertRaises(AssertionError):
      provider._get_client()
    args, kwargs = boto_client.call_args
    self.assertEqual(args, ('sesv2',))
    self.assertEqual(kwargs['region_name'], 'sa-east-1')
    self.assertEqual(kwargs['config'].retries, {'total_max_attempts': 1, 'mode': 'standard'})

  def test_template_error_does_not_call_ses(self, _boto):
    client = _ses_client()
    result = self._send(client, context=_context(customer_name=''))
    self.assertEqual((result.accepted, result.retryable, result.error_code), (False, False, 'template_context_invalid'))
    client.send_email.assert_not_called()

  def test_invalid_destination_or_sender_does_not_call_ses(self, _boto):
    client = _ses_client()
    self.assertEqual(self._send(client, destination='nope').error_code, 'ses_invalid_destination')
    with override_settings(AWS_SES_FROM_EMAIL='', DEFAULT_FROM_EMAIL='MiRubro'):
      self.assertEqual(self._send(client).error_code, 'ses_sender_not_configured')
    client.send_email.assert_not_called()


# ── Selección de proveedor (protección de entorno) ───────────────────────────

class ProviderSelectionTests(SimpleTestCase):

  def test_default_email_provider_is_fake(self):
    self.assertIsInstance(get_provider(EMAIL), FakeEmailProvider)

  @override_settings(CUSTOMER_DELIVERY_PROVIDER_EMAIL='ses')
  def test_ses_only_with_explicit_opt_in(self):
    self.assertIsInstance(get_provider(EMAIL), AmazonSESProvider)
    self.assertNotIsInstance(get_provider(D.Channel.WHATSAPP), AmazonSESProvider)

  @override_settings(CUSTOMER_DELIVERY_PROVIDER_EMAIL='sendgrid')
  def test_unknown_provider_fails_closed(self):
    with self.assertRaises(ValueError):
      get_provider(EMAIL)
    with self.assertRaises(ValueError):
      get_provider(D.Channel.WHATSAPP, 'ses')


# ── Integración con execute_delivery (12-22) ─────────────────────────────────

@override_settings(**SES_SETTINGS)
@patch('boto3.client', side_effect=AssertionError('real boto3 client must not be created in tests'))
class SESDeliveryIntegrationTests(DeliveryMixin, TestCase):

  def setUp(self):
    self.biz = _turnos_business(slug='delivery-ses')
    self.customer = self._customer(self.biz, name='Ana Pérez', email='Ana@Example.com')
    service, pro = self._agenda(self.biz)
    self.appt = self._appt(self.biz, service, self.customer, dj_timezone.now() + dt.timedelta(days=1), pro=pro)

  def _email_pending(self, **kwargs):
    kwargs.setdefault('appointment', self.appt)
    return self._pending(self.customer, EMAIL, **kwargs)

  def test_12_13_14_15_success_is_sent_not_delivered(self, _boto):
    delivery = self._email_pending()
    client = _ses_client('ses-msg-1')
    self.assertEqual(execute_delivery(delivery.pk, provider=AmazonSESProvider(client=client)), S.SENT)
    delivery.refresh_from_db()
    self.assertEqual(delivery.status, S.SENT)
    self.assertEqual(delivery.provider, D.Provider.SES)
    self.assertEqual(delivery.provider_message_id, 'ses-msg-1')
    self.assertIsNotNone(delivery.sent_at)
    self.assertIsNone(delivery.delivered_at)
    payload = client.send_email.call_args.kwargs
    self.assertEqual(payload['Destination']['ToAddresses'], [delivery.destination_snapshot])
    self.assertIn('Hola Ana Pérez', payload['Content']['Simple']['Body']['Text']['Data'])
    self.assertIn(self.biz.name, payload['Content']['Simple']['Subject']['Data'])

  def test_billing_email_is_not_reply_to_by_default(self, _boto):
    # 07D.3A.1: el email fiscal NO es contacto operativo implícito.
    self.biz.billing_profile.email = 'facturacion@negocio.com'
    self.biz.billing_profile.save()
    delivery = self._email_pending()
    self.assertIsNone(delivery.context['business_reply_to'])
    client = _ses_client()
    execute_delivery(delivery.pk, provider=AmazonSESProvider(client=client))
    self.assertNotIn('ReplyToAddresses', client.send_email.call_args.kwargs)

  def test_operational_reply_to_email_is_used(self, _boto):
    self.biz.billing_profile.email = 'facturacion@negocio.com'
    self.biz.billing_profile.save()
    CustomerCommunicationSettings.objects.create(business=self.biz, reply_to_email='turnos@negocio.com')
    delivery = self._email_pending()
    self.assertEqual(delivery.context['business_reply_to'], 'turnos@negocio.com')
    client = _ses_client()
    execute_delivery(delivery.pk, provider=AmazonSESProvider(client=client))
    payload = client.send_email.call_args.kwargs
    self.assertEqual(payload['ReplyToAddresses'], ['turnos@negocio.com'])
    # El From sigue siendo la identidad central de settings.
    self.assertIn('<notificaciones@mirubro.com.ar>', payload['FromEmailAddress'])

  def test_empty_operational_email_means_no_reply_to(self, _boto):
    CustomerCommunicationSettings.objects.create(business=self.biz, reply_to_email='')
    delivery = self._email_pending()
    client = _ses_client()
    execute_delivery(delivery.pk, provider=AmazonSESProvider(client=client))
    self.assertNotIn('ReplyToAddresses', client.send_email.call_args.kwargs)

  def test_reply_to_is_tenant_scoped(self, _boto):
    other = _turnos_business(slug='delivery-ses-other')
    CustomerCommunicationSettings.objects.create(business=other, reply_to_email='otro@negocio.com')
    delivery = self._email_pending()
    self.assertIsNone(delivery.context['business_reply_to'])

  def test_16_do_not_contact_skips_without_calling_ses(self, _boto):
    delivery = self._email_pending()
    self._consent(self.customer, EMAIL, dnc=True)
    client = _ses_client()
    self.assertEqual(execute_delivery(delivery.pk, provider=AmazonSESProvider(client=client)), S.SKIPPED)
    client.send_email.assert_not_called()

  def test_17_consent_revoked_skips(self, _boto):
    delivery = self._email_pending()
    prefs = self.customer.contact_preferences
    prefs.email_enabled = False
    prefs.save()
    client = _ses_client()
    self.assertEqual(execute_delivery(delivery.pk, provider=AmazonSESProvider(client=client)), S.SKIPPED)
    client.send_email.assert_not_called()

  def test_18_destination_changed_skips(self, _boto):
    delivery = self._email_pending()
    self.customer.email = 'otra@example.com'
    self.customer.save()
    self._consent(self.customer, EMAIL)  # consentimiento reconfirmado para el destino nuevo
    client = _ses_client()
    self.assertEqual(execute_delivery(delivery.pk, provider=AmazonSESProvider(client=client)), S.SKIPPED)
    delivery.refresh_from_db()
    self.assertEqual(delivery.skip_reason, 'destination_changed')
    client.send_email.assert_not_called()

  def test_19_duplicate_execute_calls_ses_once(self, _boto):
    delivery = self._email_pending()
    client = _ses_client()
    provider = AmazonSESProvider(client=client)
    self.assertEqual(execute_delivery(delivery.pk, provider=provider), S.SENT)
    self.assertIsNone(execute_delivery(delivery.pk, provider=provider))
    retry_due_customer_deliveries(provider=provider, now=dj_timezone.now() + dt.timedelta(hours=1))
    self.assertEqual(client.send_email.call_count, 1)

  def test_20_retryable_failure_uses_retry_infra(self, _boto):
    delivery = self._email_pending()
    client = MagicMock()
    client.send_email.side_effect = [_client_error('TooManyRequestsException', status=429),
                                     {'MessageId': 'ses-retry-ok'}]
    provider = AmazonSESProvider(client=client)
    self.assertEqual(execute_delivery(delivery.pk, provider=provider), S.FAILED)
    delivery.refresh_from_db()
    self.assertEqual(delivery.failure_code, 'ses_throttled')
    self.assertIsNotNone(delivery.next_retry_at)
    self.assertNotIn('Ana@Example.com'.lower(), (delivery.failure_message or '').lower())
    self._make_due(delivery)
    self.assertEqual(execute_delivery(delivery.pk, provider=provider), S.SENT)
    delivery.refresh_from_db()
    self.assertEqual((delivery.attempt_count, delivery.provider_message_id), (2, 'ses-retry-ok'))

  def test_21_permanent_failure_no_retry(self, _boto):
    delivery = self._email_pending()
    client = MagicMock()
    client.send_email.side_effect = _client_error(
      'MessageRejected', 'Email address is not verified. The following identities failed the check: ana@example.com',
    )
    self.assertEqual(execute_delivery(delivery.pk, provider=AmazonSESProvider(client=client)), S.FAILED)
    delivery.refresh_from_db()
    self.assertEqual(delivery.failure_code, 'ses_identity_not_verified')
    self.assertIsNone(delivery.next_retry_at)
    self.assertNotIn('ana@example.com', delivery.failure_message)

  def test_22_context_error_does_not_call_ses(self, _boto):
    delivery = self._email_pending(appointment=None)  # sin turno → sin appointment_start_at
    client = _ses_client()
    self.assertEqual(execute_delivery(delivery.pk, provider=AmazonSESProvider(client=client)), S.FAILED)
    delivery.refresh_from_db()
    self.assertEqual(delivery.failure_code, 'template_context_invalid')
    self.assertIsNone(delivery.next_retry_at)
    client.send_email.assert_not_called()

  def test_outcome_unknown_is_failed_without_retry(self, _boto):
    delivery = self._email_pending()
    client = MagicMock()
    client.send_email.side_effect = ReadTimeoutError(endpoint_url='https://email.sa-east-1.amazonaws.com')
    self.assertEqual(execute_delivery(delivery.pk, provider=AmazonSESProvider(client=client)), S.FAILED)
    delivery.refresh_from_db()
    self.assertEqual(delivery.failure_code, 'provider_exception')
    self.assertIsNone(delivery.next_retry_at)
    retry_due_customer_deliveries(provider=AmazonSESProvider(client=client), now=dj_timezone.now() + dt.timedelta(hours=1))
    self.assertEqual(client.send_email.call_count, 1)

  @override_settings(CUSTOMER_DELIVERY_PROVIDER_EMAIL='ses')
  def test_settings_opt_in_routes_execute_to_ses(self, _boto):
    delivery = self._email_pending()
    client = _ses_client('via-settings')
    with patch('apps.customers.delivery_providers.AmazonSESProvider._get_client', return_value=client):
      self.assertEqual(execute_delivery(delivery.pk), S.SENT)
    delivery.refresh_from_db()
    self.assertEqual((delivery.provider, delivery.provider_message_id), (D.Provider.SES, 'via-settings'))

  def test_command_execute_provider_ses(self, _boto):
    delivery = self._email_pending()
    client = _ses_client('via-command')
    out = StringIO()
    with patch('apps.customers.delivery_providers.AmazonSESProvider._get_client', return_value=client):
      call_command('customer_deliveries', 'execute', '--id', str(delivery.pk), '--provider', 'ses', stdout=out)
    self.assertIn('status=sent', out.getvalue())
    self.assertIn('provider=ses', out.getvalue())
    self.assertNotIn(delivery.destination_snapshot, out.getvalue())

  def test_api_shows_provider_but_not_message_id(self, _boto):
    from rest_framework.test import APIClient

    from apps.appointments.tests.test_customer_core_access import _login

    delivery = self._email_pending()
    execute_delivery(delivery.pk, provider=AmazonSESProvider(client=_ses_client('secret-msg-id')))
    api = APIClient()
    _login(api, self.biz, 'viewer')
    response = api.get(f'/api/v1/customers/{self.customer.pk}/deliveries/')
    self.assertEqual(response.status_code, 200, response.content)
    row = response.json()['results'][0]
    self.assertEqual((row['provider_display'], row['is_simulated'], row['status']), ('Amazon SES', False, 'sent'))
    self.assertNotIn('secret-msg-id', response.content.decode())


# ── "Email para respuestas" (CUSTOMER 07D.3A.1) ──────────────────────────────

class CommunicationSettingsAPITests(TestCase):
  URL = '/api/v1/appointments/communication-settings/'

  def setUp(self):
    from rest_framework.test import APIClient

    self.biz = _turnos_business(slug='comm-settings')
    self.api = APIClient()

  def _as(self, role, biz=None):
    from apps.appointments.tests.test_customer_core_access import _login

    _login(self.api, biz or self.biz, role)

  def test_default_empty_without_creating_row(self):
    self._as('owner')
    resp = self.api.get(self.URL)
    self.assertEqual(resp.status_code, 200, resp.content)
    self.assertEqual(resp.json()['reply_to_email'], '')
    self.assertFalse(CustomerCommunicationSettings.objects.exists())

  def test_owner_and_admin_can_set_and_clear(self):
    for role, email in (('owner', 'Turnos@Negocio.COM'), ('admin', '')):
      with self.subTest(role=role):
        self._as(role)
        resp = self.api.patch(self.URL, {'reply_to_email': f'  {email} '}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
    row = CustomerCommunicationSettings.objects.get(business=self.biz)
    self.assertEqual(row.reply_to_email, '')
    self._as('owner')
    self.api.patch(self.URL, {'reply_to_email': 'Turnos@Negocio.COM'}, format='json')
    row.refresh_from_db()
    self.assertEqual(row.reply_to_email, 'Turnos@negocio.com')  # dominio normalizado

  def test_invalid_email_rejected(self):
    self._as('owner')
    for bad in ('no-es-email', 'a@b', 'x' * 250 + '@negocio.com'):
      with self.subTest(bad=bad):
        self.assertEqual(self.api.patch(self.URL, {'reply_to_email': bad}, format='json').status_code, 400)

  def test_manager_reads_but_cannot_modify(self):
    CustomerCommunicationSettings.objects.create(business=self.biz, reply_to_email='turnos@negocio.com')
    self._as('manager')
    resp = self.api.get(self.URL)
    self.assertEqual((resp.status_code, resp.json()['reply_to_email']), (200, 'turnos@negocio.com'))
    self.assertEqual(self.api.patch(self.URL, {'reply_to_email': 'otro@x.com'}, format='json').status_code, 403)
    self.assertEqual(CustomerCommunicationSettings.objects.get(business=self.biz).reply_to_email, 'turnos@negocio.com')

  def test_viewer_cannot_read_or_modify(self):
    self._as('viewer')
    self.assertEqual(self.api.get(self.URL).status_code, 403)
    self.assertEqual(self.api.patch(self.URL, {'reply_to_email': 'a@b.com'}, format='json').status_code, 403)

  def test_business_cannot_change_from(self):
    self._as('owner')
    resp = self.api.patch(self.URL, {'from_email': 'yo@negocio.com', 'reply_to_email': 'turnos@negocio.com'}, format='json')
    self.assertEqual(resp.status_code, 200)
    self.assertNotIn('from_email', resp.json())
    self.assertEqual(set(resp.json()), {'reply_to_email', 'updated_at'})
    with override_settings(**SES_SETTINGS):
      self.assertIn('<notificaciones@mirubro.com.ar>', ses_from_header(self.biz.name))

  def test_tenant_isolation(self):
    other = _turnos_business(slug='comm-settings-other')
    CustomerCommunicationSettings.objects.create(business=other, reply_to_email='otro@negocio.com')
    self._as('owner')
    self.assertEqual(self.api.get(self.URL).json()['reply_to_email'], '')
    self.api.patch(self.URL, {'reply_to_email': 'mio@negocio.com'}, format='json')
    self.assertEqual(CustomerCommunicationSettings.objects.get(business=other).reply_to_email, 'otro@negocio.com')
