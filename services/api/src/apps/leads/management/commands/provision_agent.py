"""Aprovisionamiento manual de la integración con el agente de WhatsApp (AGENT 02A).

Crea/reutiliza, en una sola transacción:
  - AgentInstance  (--external-id, --name)
  - AgentCredential (--key-id; secreto cifrado con AGENT_SECRET_ENCRYPTION_KEY)
  - AgentChannel   (--business-id + --phone-number-id [--provider])

  python manage.py provision_agent --external-id dental-agent-prod --name "Dental agent prod"
  AGENT_PROVISION_SECRET=... python manage.py provision_agent --external-id dental-agent-prod --key-id k1
  python manage.py provision_agent --external-id dental-agent-prod --key-id k1 --secret-stdin < secret.txt
  python manage.py provision_agent --external-id dental-agent-prod --business-id 42 --phone-number-id 1234567890

El secreto NUNCA se acepta como argumento (quedaría en el historial del shell):
se lee de la env `AGENT_PROVISION_SECRET` o, con `--secret-stdin`, de stdin
(prompt oculto con getpass si stdin es una terminal). Nunca se imprime.

Autorizaciones de WhatsApp (PROD-04B; solo personal de plataforma, `--actor-email`):

  # Crear una autorización del Business y asociarla al canal (token por stdin)
  python manage.py provision_agent --external-id X --business-id 42 --phone-number-id 123 \
      --waba-id 456 --create-whatsapp-authorization --whatsapp-token-stdin --actor-email ops@x
  # Asociar el canal a una autorización existente (p. ej. compartida)
  ... --business-id 42 --phone-number-id 123 --waba-id 456 --whatsapp-authorization-id <uuid> --actor-email ops@x
  # Rotar (token nuevo por stdin/env) o revocar localmente
  python manage.py provision_agent --rotate-whatsapp-authorization <uuid> --whatsapp-token-stdin --actor-email ops@x
  python manage.py provision_agent --revoke-whatsapp-authorization <uuid> --actor-email ops@x

El token de Meta, igual que el secreto, nunca va por argumento: env
`WHATSAPP_PROVISION_TOKEN` o `--whatsapp-token-stdin`. Revocar o rotar acá NO
lo revoca ante Meta. `--platform-whatsapp-authorization` crea una
autorización sin dueño (excepcional).

Idempotente para desarrollo: re-ejecutar con los mismos datos no duplica nada.
Una key_id existente no se re-cifra ni se rota (rotar = nueva --key-id). Un
phone_number_id activo en otro Business/instancia es un error (reasignar =
desactivar el canal anterior a mano y volver a correr).
"""
from __future__ import annotations

import getpass
import os
import sys

from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.business.models import Business
from apps.leads.crypto import AgentSecretEncryptionError
from apps.leads.models import AgentChannel, AgentCredential, AgentInstance
from apps.leads.services import whatsapp_authorizations as wa

SECRET_ENV = 'AGENT_PROVISION_SECRET'
SECRET_MIN_LENGTH = 32
WHATSAPP_TOKEN_ENV = 'WHATSAPP_PROVISION_TOKEN'


class Command(BaseCommand):
    help = 'Crea/configura AgentInstance, AgentCredential y AgentChannel (el secreto se lee de env o stdin).'

    def add_arguments(self, parser):
        parser.add_argument('--external-id', help='agent_instance_id del contrato ([a-z0-9-]{3,64})')
        parser.add_argument('--name', help='Nombre interno de la instancia (default: external-id)')
        parser.add_argument('--key-id', help='key_id público de la credencial a crear')
        parser.add_argument(
            '--secret-stdin', action='store_true',
            help=f'Leer el secreto de stdin (oculto si es terminal) en vez de la env {SECRET_ENV}',
        )
        parser.add_argument('--business-id', type=int)
        parser.add_argument('--provider', choices=AgentChannel.Provider.values, default=AgentChannel.Provider.WHATSAPP_CLOUD)
        parser.add_argument('--phone-number-id')
        # ── PROD-04B: autorizaciones de WhatsApp ──
        parser.add_argument('--actor-email', help='Personal de plataforma que ejecuta (superadmin/operations)')
        parser.add_argument('--waba-id', help='WhatsApp Business Account del número')
        parser.add_argument('--create-whatsapp-authorization', action='store_true')
        parser.add_argument('--platform-whatsapp-authorization', action='store_true',
                            help='Crear la autorización SIN dueño (plataforma; excepcional)')
        parser.add_argument('--whatsapp-authorization-id', help='Asociar el canal a esta autorización existente')
        parser.add_argument('--rotate-whatsapp-authorization', metavar='UUID')
        parser.add_argument('--revoke-whatsapp-authorization', metavar='UUID')
        parser.add_argument('--whatsapp-expires-at', help='Vencimiento ISO 8601 con zona (opcional)')
        parser.add_argument(
            '--whatsapp-token-stdin', action='store_true',
            help=f'Leer el token de Meta de stdin en vez de la env {WHATSAPP_TOKEN_ENV}',
        )

    def handle(self, *args, **opts):
        maintenance = opts['rotate_whatsapp_authorization'] or opts['revoke_whatsapp_authorization']
        if maintenance:
            return self._maintenance(opts)
        if not opts['external_id']:
            raise CommandError('--external-id es obligatorio para aprovisionar.')
        if (opts['business_id'] is None) != (opts['phone_number_id'] is None):
            raise CommandError('--business-id y --phone-number-id van juntos.')
        if opts['secret_stdin'] and not opts['key_id']:
            raise CommandError('--secret-stdin requiere --key-id.')
        linking = opts['create_whatsapp_authorization'] or opts['whatsapp_authorization_id']
        if opts['create_whatsapp_authorization'] and opts['whatsapp_authorization_id']:
            raise CommandError('Usar --create-whatsapp-authorization o --whatsapp-authorization-id, no ambos.')
        if linking and (opts['business_id'] is None or not opts['waba_id']):
            raise CommandError('Asociar WhatsApp requiere --business-id, --phone-number-id y --waba-id.')
        if opts['platform_whatsapp_authorization'] and not opts['create_whatsapp_authorization']:
            raise CommandError('--platform-whatsapp-authorization solo con --create-whatsapp-authorization.')
        if opts['whatsapp_token_stdin'] and opts['secret_stdin']:
            raise CommandError('Un solo secreto por stdin: usar la env para el otro.')
        actor = self._actor(opts) if linking else None

        try:
            with transaction.atomic():
                instance = self._instance(opts)
                if opts['key_id']:
                    self._credential(instance, opts)
                if opts['business_id'] is not None:
                    channel = self._channel(instance, opts)
                    if linking:
                        self._link_whatsapp(channel, actor, opts)
        except IntegrityError as exc:
            # Carrera con otra alta concurrente: no se filtra el detalle SQL.
            raise CommandError('Conflicto de unicidad al aprovisionar (reintentar y revisar el estado).') from exc
        except AgentSecretEncryptionError as exc:
            raise CommandError(str(exc)) from exc
        except wa.WhatsAppAuthorizationError as exc:
            raise CommandError(f'{exc.code}: {exc}') from exc

    # ── WhatsApp (PROD-04B) ────────────────────────────────────────────────

    def _actor(self, opts):
        email = (opts['actor_email'] or '').strip()
        if not email:
            raise CommandError('Las operaciones de WhatsApp requieren --actor-email.')
        users = list(get_user_model().objects.filter(email__iexact=email)[:2])
        if len(users) != 1:
            raise CommandError('--actor-email no identifica a un único usuario.')
        return users[0]

    def _expires_at(self, opts):
        raw = opts['whatsapp_expires_at']
        if not raw:
            return None
        value = parse_datetime(raw)
        if value is None:
            raise CommandError('--whatsapp-expires-at no es una fecha ISO 8601 válida.')
        return value

    def _read_token(self, opts) -> str:
        return self._read_value(
            stdin=opts['whatsapp_token_stdin'], env=WHATSAPP_TOKEN_ENV, flag='--whatsapp-token-stdin',
            prompt='Token de Meta (no se muestra): ', min_length=wa.TOKEN_MIN_LENGTH,
        )

    def _link_whatsapp(self, channel: AgentChannel, actor, opts) -> None:
        if opts['create_whatsapp_authorization']:
            platform = opts['platform_whatsapp_authorization']
            token = self._read_token(opts)
            authorization = wa.create_whatsapp_authorization(
                token=token, actor=actor, platform=platform,
                owner_business=None if platform else channel.business, expires_at=self._expires_at(opts),
            )
            del token
            self.stdout.write(self.style.SUCCESS(f'WhatsAppAuthorization creada: {authorization}'))
            authorization_id = authorization.pk
        else:
            authorization_id = opts['whatsapp_authorization_id']
        wa.associate_channel(
            channel_id=channel.pk, authorization_id=authorization_id, waba_id=opts['waba_id'], actor=actor,
        )
        self.stdout.write(self.style.SUCCESS(f'AgentChannel {channel.pk} asociado a WhatsAppAuthorization {authorization_id}'))

    def _maintenance(self, opts) -> None:
        if opts['rotate_whatsapp_authorization'] and opts['revoke_whatsapp_authorization']:
            raise CommandError('Rotar o revocar, no ambos.')
        actor = self._actor(opts)
        try:
            if opts['revoke_whatsapp_authorization']:
                authorization = wa.revoke_whatsapp_authorization(
                    authorization_id=opts['revoke_whatsapp_authorization'], actor=actor,
                )
                self.stdout.write(self.style.SUCCESS(f'Revocada localmente: {authorization}'))
            else:
                token = self._read_token(opts)
                authorization = wa.rotate_whatsapp_authorization(
                    authorization_id=opts['rotate_whatsapp_authorization'], token=token, actor=actor,
                    expires_at=self._expires_at(opts),
                )
                del token
                self.stdout.write(self.style.SUCCESS(f'Rotada: {authorization}'))
        except wa.WhatsAppAuthorizationError as exc:
            raise CommandError(f'{exc.code}: {exc}') from exc
        except (ValidationError, ValueError) as exc:
            raise CommandError('Identificador de autorización inválido.') from exc
        except AgentSecretEncryptionError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.WARNING(
            '  Solo local: el token anterior sigue válido ante Meta hasta revocarlo allá.'
        ))

    # ── AgentInstance ──────────────────────────────────────────────────────

    def _instance(self, opts) -> AgentInstance:
        external_id = opts['external_id']
        instance = AgentInstance.objects.filter(external_id=external_id).first()
        if instance is not None:
            if opts['name'] and opts['name'] != instance.name:
                self.stdout.write(self.style.WARNING('  AgentInstance existente: --name ignorado (no se renombra).'))
            if not instance.is_enabled:
                self.stdout.write(self.style.WARNING('  AgentInstance deshabilitada (is_enabled=False).'))
            self.stdout.write(f'AgentInstance existente: id={instance.pk} external_id={instance.external_id}')
            return instance

        instance = AgentInstance(external_id=external_id, name=opts['name'] or external_id)
        self._validate(instance)
        instance.save()
        self.stdout.write(self.style.SUCCESS(f'AgentInstance creada: id={instance.pk} external_id={instance.external_id}'))
        return instance

    # ── AgentCredential ────────────────────────────────────────────────────

    def _credential(self, instance: AgentInstance, opts) -> AgentCredential:
        key_id = opts['key_id']
        credential = AgentCredential.objects.filter(key_id=key_id).first()
        if credential is not None:
            if credential.agent_instance_id != instance.pk:
                raise CommandError(f'key_id {key_id} ya pertenece a otra AgentInstance.')
            self.stdout.write(
                f'AgentCredential existente: key_id={credential.key_id} status={credential.status} '
                '(secreto sin cambios; rotar = nueva --key-id)'
            )
            return credential

        secret = self._read_secret(opts)
        credential = AgentCredential(agent_instance=instance, key_id=key_id)
        credential.set_secret(secret)
        del secret
        self._validate(credential, exclude=['encrypted_secret'])
        credential.save()
        self.stdout.write(self.style.SUCCESS(f'AgentCredential creada: key_id={credential.key_id} status={credential.status}'))
        return credential

    def _read_secret(self, opts) -> str:
        return self._read_value(
            stdin=opts['secret_stdin'], env=SECRET_ENV, flag='--secret-stdin', prompt='Secreto del agente (no se muestra): ',
            min_length=SECRET_MIN_LENGTH,
        )

    @staticmethod
    def _read_value(*, stdin: bool, env: str, flag: str, prompt: str, min_length: int) -> str:
        """Secreto desde stdin (oculto si es terminal) o env; nunca argv ni stdout."""
        if stdin:
            value = getpass.getpass(prompt) if sys.stdin.isatty() else sys.stdin.readline()
            value = value.rstrip('\r\n')
        else:
            value = os.environ.get(env, '')
        if not value:
            raise CommandError(f'Falta el secreto: definir {env} o usar {flag}.')
        if len(value) < min_length:
            raise CommandError(f'El secreto debe tener al menos {min_length} caracteres.')
        return value

    # ── AgentChannel ───────────────────────────────────────────────────────

    def _channel(self, instance: AgentInstance, opts) -> AgentChannel:
        business = Business.objects.filter(pk=opts['business_id']).first()
        if business is None:
            raise CommandError(f'Business {opts["business_id"]} no existe.')

        provider, phone_number_id = opts['provider'], opts['phone_number_id']
        active = (
            AgentChannel.objects.select_for_update()
            .filter(provider=provider, phone_number_id=phone_number_id, is_active=True)
            .first()
        )
        if active is not None:
            if active.business_id == business.pk and active.agent_instance_id == instance.pk:
                self.stdout.write(f'AgentChannel activo existente: id={active.pk}')
                return active
            raise CommandError(
                f'{provider}:{phone_number_id} ya está activo en otro canal (id={active.pk}). '
                'Desactivarlo primero para reasignar.'
            )

        channel = AgentChannel(
            provider=provider, phone_number_id=phone_number_id, agent_instance=instance, business=business,
        )
        self._validate(channel)
        channel.save()
        self.stdout.write(self.style.SUCCESS(
            f'AgentChannel creado: id={channel.pk} {provider}:{phone_number_id} → business {business.pk}'
        ))
        return channel

    @staticmethod
    def _validate(obj, exclude=None) -> None:
        try:
            obj.full_clean(exclude=exclude, validate_constraints=False)
        except ValidationError as exc:
            raise CommandError(f'Datos inválidos: {exc.message_dict}') from exc
