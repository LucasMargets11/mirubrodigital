"""PROD-03A: configuración individual de Recepcionista IA."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.business.models import Business
from apps.leads import errors
from apps.leads.models import (
    RECEPTIONIST_MAX_FAQS,
    RECEPTIONIST_MAX_SERVICES,
    AgentChannel,
    AgentCredential,
    ReceptionistConfig,
)
from apps.leads.services.receptionist_config import receptionist_config_for_agent

from .factories import make_business, make_channel, make_instance


def complete(**overrides) -> dict:
    data = dict(
        assistant_name='Sofía',
        business_category='Peluquería',
        business_description='Peluquería unisex en el centro.',
        welcome_message='¡Hola! Soy Sofía, ¿en qué te ayudo?',
        business_hours='Lunes a viernes de 9 a 19.',
        services=[{'name': 'Corte', 'description': 'Corte y peinado.'}],
    )
    data.update(overrides)
    return data


def make_config(business: Business, **fields) -> ReceptionistConfig:
    return ReceptionistConfig.objects.create(business=business, **fields)


class CreationAndValidationTests(TestCase):
    def setUp(self):
        self.business = make_business('recep-a')

    def test_default_is_an_empty_draft_version_1(self):
        config = make_config(self.business)
        self.assertEqual(config.status, ReceptionistConfig.Status.DRAFT)
        self.assertEqual(config.version, 1)
        self.assertEqual((config.services, config.faqs), ([], []))
        self.assertEqual((config.tone, config.language), ('warm', 'es-AR'))
        self.assertFalse(config.is_ready)

    def test_complete_config_can_be_ready(self):
        config = make_config(self.business, status='ready', **complete())
        self.assertTrue(config.is_ready)
        self.assertEqual(config.missing_for_ready(), [])

    def test_full_content_round_trips(self):
        config = make_config(
            self.business, **complete(
                custom_instructions='Ofrecé siempre el turno de la mañana primero.',
                tone='formal', language='es', operational_info='Pagos con transferencia.',
                reference_info='Usamos productos sin TACC.', handoff_rules='Reclamos: derivar a una persona.',
                faqs=[{'question': '¿Hacen color?', 'answer': 'Sí, con turno previo.'}],
            ),
        )
        config.refresh_from_db()
        self.assertEqual(config.faqs, [{'question': '¿Hacen color?', 'answer': 'Sí, con turno previo.'}])
        self.assertEqual(config.tone, 'formal')

    def test_invalid_choices_are_rejected(self):
        for field, value in (('tone', 'aggressive'), ('language', 'en'), ('status', 'active')):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                make_config(make_business(f'recep-choice-{field}'), **{field: value})

    def test_invalid_choices_rejected_by_db_too(self):
        config = make_config(self.business)
        for field, value in (('tone', 'aggressive'), ('language', 'en'), ('status', 'active'), ('version', 0)):
            with self.subTest(field=field), self.assertRaises(IntegrityError), transaction.atomic():
                ReceptionistConfig.objects.filter(pk=config.pk).update(**{field: value})


class IncompleteConfigTests(TestCase):
    def test_each_required_piece_blocks_ready(self):
        for index, field in enumerate((
            'assistant_name', 'business_category', 'business_description', 'welcome_message', 'business_hours',
        )):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError) as ctx:
                    make_config(make_business(f'recep-inc-{index}'), status='ready', **complete(**{field: ''}))
                self.assertIn(field, str(ctx.exception))

    def test_whitespace_only_counts_as_missing(self):
        with self.assertRaises(ValidationError):
            make_config(make_business('recep-ws'), status='ready', **complete(assistant_name='   '))

    def test_without_services_is_not_ready(self):
        with self.assertRaises(ValidationError) as ctx:
            make_config(make_business('recep-nosvc'), status='ready', **complete(services=[]))
        self.assertIn('services', str(ctx.exception))

    def test_incomplete_draft_is_allowed_but_not_ready(self):
        config = make_config(make_business('recep-draft'), assistant_name='Sofía')
        self.assertFalse(config.is_ready)
        self.assertIn('business_hours', config.missing_for_ready())

    def test_db_rejects_ready_without_minimum_even_via_update(self):
        config = make_config(make_business('recep-upd'), **complete(business_hours=''))
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReceptionistConfig.objects.filter(pk=config.pk).update(status='ready')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReceptionistConfig.objects.filter(pk=config.pk).update(status='ready', business_hours='9 a 19', services=[])

    def test_emptying_a_ready_config_is_rejected(self):
        config = make_config(make_business('recep-empty'), status='ready', **complete())
        config.welcome_message = ''
        with self.assertRaises(ValidationError):
            config.save()


class FieldLimitTests(TestCase):
    def setUp(self):
        self.business = make_business('recep-limits')

    def test_text_lengths(self):
        for field, limit in (
            ('assistant_name', 80), ('business_category', 80), ('business_description', 1000),
            ('custom_instructions', 4000), ('welcome_message', 500), ('operational_info', 2000),
            ('business_hours', 1000), ('reference_info', 4000), ('handoff_rules', 2000),
        ):
            with self.subTest(field=field):
                config = ReceptionistConfig(business=self.business, **{field: 'x' * limit})
                config.full_clean(exclude=['business'])
                config = ReceptionistConfig(business=self.business, **{field: 'x' * (limit + 1)})
                with self.assertRaises(ValidationError):
                    config.full_clean(exclude=['business'])

    def test_null_character_rejected(self):
        with self.assertRaises(ValidationError):
            make_config(self.business, business_description='hola\x00')

    def test_list_limits(self):
        services = [{'name': f'S{i}'} for i in range(RECEPTIONIST_MAX_SERVICES)]
        make_config(self.business, services=services)
        for field, value in (
            ('services', [{'name': f'S{i}'} for i in range(RECEPTIONIST_MAX_SERVICES + 1)]),
            ('faqs', [{'question': f'Q{i}', 'answer': 'a'} for i in range(RECEPTIONIST_MAX_FAQS + 1)]),
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                make_config(make_business(f'recep-max-{field}'), **{field: value})

    def test_item_shapes(self):
        bad = {
            'services': [
                'Corte', {}, {'description': 'sin nombre'}, {'name': ''}, {'name': 'Corte', 'price': 100},
                {'name': 1}, {'name': 'x' * 121}, {'name': 'Corte', 'description': 'x' * 501},
            ],
            'faqs': [
                {'question': '¿?'}, {'question': '¿?', 'answer': ''}, {'question': 'x' * 301, 'answer': 'a'},
                {'question': '¿?', 'answer': 'x' * 1001},
            ],
        }
        for field, items in bad.items():
            for index, item in enumerate(items):
                with self.subTest(field=field, item=item), self.assertRaises(ValidationError):
                    make_config(make_business(f'recep-shape-{field}-{index}'), **{field: [item]})
        with self.assertRaises(ValidationError):
            make_config(make_business('recep-shape-dict'), services={'name': 'Corte'})

    def test_duplicate_items_rejected_case_insensitive(self):
        with self.assertRaises(ValidationError):
            make_config(self.business, services=[{'name': 'Corte'}, {'name': ' corte '}])
        with self.assertRaises(ValidationError):
            make_config(
                make_business('recep-dup-faq'),
                faqs=[{'question': '¿Abren?', 'answer': 'Sí'}, {'question': '¿abren?', 'answer': 'No'}],
            )


class IsolationAndUniquenessTests(TestCase):
    def setUp(self):
        self.a = make_business('recep-iso-a')
        self.b = make_business('recep-iso-b')

    def test_one_config_per_business(self):
        make_config(self.a)
        with self.assertRaises(ValidationError):
            make_config(self.a)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReceptionistConfig.objects.bulk_create([ReceptionistConfig(business=self.a)])

    def test_two_businesses_are_independent(self):
        config_a = make_config(self.a, **complete(assistant_name='Ana'))
        config_b = make_config(self.b, **complete(assistant_name='Bruno'))
        config_a.assistant_name = 'Ana María'
        config_a.save()
        config_b.refresh_from_db()
        self.assertEqual((config_b.assistant_name, config_b.version), ('Bruno', 1))
        self.assertEqual(self.a.receptionist_config.assistant_name, 'Ana María')

    def test_business_is_immutable(self):
        config = make_config(self.a)
        config.business = self.b
        with self.assertRaises(ValidationError):
            config.save()
        config.refresh_from_db()
        self.assertEqual(config.business_id, self.a.id)

    def test_deleting_business_deletes_only_its_config(self):
        make_config(self.a)
        make_config(self.b)
        self.a.delete()
        self.assertEqual(list(ReceptionistConfig.objects.values_list('business_id', flat=True)), [self.b.id])


class AgentRelationTests(TestCase):
    """La config se ve solo a través de un canal activo de la instancia."""

    def setUp(self):
        self.a = make_business('recep-rel-a')
        self.b = make_business('recep-rel-b')
        self.instance = make_instance('recep-agent-1')
        self.other = make_instance('recep-agent-2')
        # Una instancia atiende dos negocios: no representa un único negocio
        make_channel(self.instance, self.a, phone_number_id='111')
        make_channel(self.instance, self.b, phone_number_id='222')
        make_channel(self.other, make_business('recep-rel-c'), phone_number_id='333')
        self.config_a = make_config(self.a, **complete(assistant_name='Ana'))
        self.config_b = make_config(self.b, **complete(assistant_name='Bruno'))

    def resolve(self, instance, phone, business):
        return receptionist_config_for_agent(instance, phone_number_id=phone, business_id=business.id)

    def assertCode(self, code, *args):
        with self.assertRaises(errors.AgentApiError) as ctx:
            self.resolve(*args)
        self.assertEqual(ctx.exception.error_code, code)

    def test_each_channel_resolves_its_own_business(self):
        self.assertEqual(self.resolve(self.instance, '111', self.a), self.config_a)
        self.assertEqual(self.resolve(self.instance, '222', self.b), self.config_b)

    def test_foreign_instance_cannot_read_the_config(self):
        self.assertCode('channel_disabled', self.other, '111', self.a)

    def test_business_id_must_match_the_channel(self):
        self.assertCode('business_mismatch', self.instance, '111', self.b)

    def test_inactive_channel_or_business(self):
        AgentChannel.objects.filter(phone_number_id='111').update(is_active=False, deactivated_at='2026-11-26T00:00Z')
        self.assertCode('channel_disabled', self.instance, '111', self.a)
        Business.objects.filter(pk=self.b.pk).update(status='suspended')
        self.assertCode('business_inactive', self.instance, '222', self.b)

    def test_unknown_phone_number(self):
        self.assertCode('channel_disabled', self.instance, '999', self.a)

    def test_channel_without_config_is_none(self):
        business = make_business('recep-rel-d')
        make_channel(self.instance, business, phone_number_id='444')
        self.assertIsNone(self.resolve(self.instance, '444', business))


class PreservationTests(TestCase):
    def test_new_business_gets_no_config_automatically(self):
        business = make_business('recep-new')
        self.assertFalse(ReceptionistConfig.objects.filter(business=business).exists())

    def test_version_counts_content_changes_only(self):
        config = make_config(make_business('recep-ver'), **complete())
        config.save()
        self.assertEqual(config.version, 1)
        config.status = 'ready'
        config.save()
        self.assertEqual(config.version, 1)
        config.faqs = [{'question': '¿Abren sábados?', 'answer': 'No.'}]
        config.save()
        config.refresh_from_db()
        self.assertEqual((config.version, config.status), (2, 'ready'))

    def test_stale_instance_cannot_rewind_the_version(self):
        business = make_business('recep-stale')
        make_config(business, **complete())
        first = ReceptionistConfig.objects.get(business=business)
        second = ReceptionistConfig.objects.get(business=business)
        first.welcome_message = 'Hola 1'
        first.save()
        second.welcome_message = 'Hola 2'
        second.save()
        self.assertEqual(ReceptionistConfig.objects.get(business=business).version, 3)

    def test_failed_save_keeps_the_stored_config(self):
        config = make_config(make_business('recep-keep'), status='ready', **complete())
        config.business_hours = ''
        with self.assertRaises(ValidationError):
            config.save()
        stored = ReceptionistConfig.objects.get(pk=config.pk)
        self.assertEqual((stored.business_hours, stored.version), ('Lunes a viernes de 9 a 19.', 1))


class NoSecretsNoCapabilitiesTests(TestCase):
    def test_model_has_no_secret_capability_or_connection_fields(self):
        names = {field.name for field in ReceptionistConfig._meta.get_fields()}
        forbidden = (
            'token', 'secret', 'key', 'password', 'credential', 'phone_number', 'channel', 'agent',
            'agenda', 'permission', 'entitlement', 'usage', 'quota', 'plan', 'subscription', 'enabled',
        )
        self.assertEqual([n for n in names if any(word in n for word in forbidden)], [])
        related = [f for f in ReceptionistConfig._meta.get_fields() if f.is_relation]
        self.assertEqual([f.related_model for f in related], [Business])

    def test_business_data_is_not_duplicated(self):
        names = {field.name for field in ReceptionistConfig._meta.get_fields()}
        for reused in ('name', 'address', 'commercial_address', 'phone', 'whatsapp_phone', 'timezone', 'email'):
            self.assertNotIn(reused, names)

    def test_secret_looking_text_is_rejected_everywhere(self):
        samples = (
            'sk-proj-ABCDEFGHIJKLMNOPQRSTUV',
            'EAAGm0PX4ZCpsBAAbcdefghijklmnopqrstuvwxyz',
            'gAAAAABl' + 'a' * 40,
            '-----BEGIN RSA PRIVATE KEY-----',
            'Authorization: Bearer abcdefghijklmnopqrstu',
            'AKIAABCDEFGHIJKLMNOP',
        )
        for index, sample in enumerate(samples):
            for field, value in (
                ('custom_instructions', f'Usá esta clave {sample}'),
                ('reference_info', sample),
                ('services', [{'name': 'Corte', 'description': sample}]),
                ('faqs', [{'question': '¿Clave?', 'answer': sample}]),
            ):
                with self.subTest(sample=index, field=field), self.assertRaises(ValidationError):
                    make_config(make_business(f'recep-secret-{index}-{field}'), **{field: value})

    def test_ordinary_text_is_not_mistaken_for_a_secret(self):
        make_config(
            make_business('recep-ok-text'),
            custom_instructions='Pedí el nombre y el motivo. Skin care: sk-ii no se vende acá.',
            reference_info='Clave wifi para clientes: pedila en el mostrador.',
        )

    def test_ready_config_grants_no_capability(self):
        from apps.appointments.services.agenda_access import has_agenda_access

        business = make_business('recep-cap')
        make_config(business, status='ready', **complete(custom_instructions='Tenés agenda y podés reservar.'))
        self.assertFalse(has_agenda_access(business))
        self.assertFalse(AgentCredential.objects.exists())
        self.assertFalse(AgentChannel.objects.filter(business=business).exists())
