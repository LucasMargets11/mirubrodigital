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

Idempotente para desarrollo: re-ejecutar con los mismos datos no duplica nada.
Una key_id existente no se re-cifra ni se rota (rotar = nueva --key-id). Un
phone_number_id activo en otro Business/instancia es un error (reasignar =
desactivar el canal anterior a mano y volver a correr).
"""
from __future__ import annotations

import getpass
import os
import sys

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.business.models import Business
from apps.leads.crypto import AgentSecretEncryptionError
from apps.leads.models import AgentChannel, AgentCredential, AgentInstance

SECRET_ENV = 'AGENT_PROVISION_SECRET'
SECRET_MIN_LENGTH = 32


class Command(BaseCommand):
    help = 'Crea/configura AgentInstance, AgentCredential y AgentChannel (el secreto se lee de env o stdin).'

    def add_arguments(self, parser):
        parser.add_argument('--external-id', required=True, help='agent_instance_id del contrato ([a-z0-9-]{3,64})')
        parser.add_argument('--name', help='Nombre interno de la instancia (default: external-id)')
        parser.add_argument('--key-id', help='key_id público de la credencial a crear')
        parser.add_argument(
            '--secret-stdin', action='store_true',
            help=f'Leer el secreto de stdin (oculto si es terminal) en vez de la env {SECRET_ENV}',
        )
        parser.add_argument('--business-id', type=int)
        parser.add_argument('--provider', choices=AgentChannel.Provider.values, default=AgentChannel.Provider.WHATSAPP_CLOUD)
        parser.add_argument('--phone-number-id')

    def handle(self, *args, **opts):
        if (opts['business_id'] is None) != (opts['phone_number_id'] is None):
            raise CommandError('--business-id y --phone-number-id van juntos.')
        if opts['secret_stdin'] and not opts['key_id']:
            raise CommandError('--secret-stdin requiere --key-id.')

        try:
            with transaction.atomic():
                instance = self._instance(opts)
                if opts['key_id']:
                    self._credential(instance, opts)
                if opts['business_id'] is not None:
                    self._channel(instance, opts)
        except IntegrityError as exc:
            # Carrera con otra alta concurrente: no se filtra el detalle SQL.
            raise CommandError('Conflicto de unicidad al aprovisionar (reintentar y revisar el estado).') from exc
        except AgentSecretEncryptionError as exc:
            raise CommandError(str(exc)) from exc

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
        if opts['secret_stdin']:
            if sys.stdin.isatty():
                secret = getpass.getpass('Secreto del agente (no se muestra): ')
            else:
                secret = sys.stdin.readline()
            secret = secret.rstrip('\r\n')
        else:
            secret = os.environ.get(SECRET_ENV, '')
        if not secret:
            raise CommandError(f'Falta el secreto: definir {SECRET_ENV} o usar --secret-stdin.')
        if len(secret) < SECRET_MIN_LENGTH:
            raise CommandError(f'El secreto debe tener al menos {SECRET_MIN_LENGTH} caracteres.')
        return secret

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
