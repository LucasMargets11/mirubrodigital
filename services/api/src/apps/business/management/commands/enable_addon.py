"""
Management command para habilitar add-ons en una subscription.

Uso:
    python manage.py enable_addon <business_id> <addon_code>

Ejemplos:
    python manage.py enable_addon 5 invoices_module
    python manage.py enable_addon 5 customers_module
"""
from django.core.management.base import BaseCommand, CommandError
from apps.business.models import Business, SubscriptionAddon


class Command(BaseCommand):
    help = 'Habilita un add-on para un business específico'

    def add_arguments(self, parser):
        parser.add_argument('business_id', type=int, help='ID del business')
        parser.add_argument('addon_code', type=str, help='Código del add-on (invoices_module, customers_module, etc.)')
        parser.add_argument(
            '--quantity',
            type=int,
            default=1,
            help='Cantidad del add-on (default: 1)'
        )

    def handle(self, *args, **options):
        business_id = options['business_id']
        addon_code = options['addon_code']
        quantity = options['quantity']

        # Validar business
        try:
            business = Business.objects.select_related('subscription').get(id=business_id)
        except Business.DoesNotExist:
            raise CommandError(f'Business con ID {business_id} no encontrado')

        # Validar subscription
        try:
            subscription = business.subscription
        except Exception:
            raise CommandError(f'El business {business_id} no tiene una subscription válida')

        # Validar código de addon
        valid_addons = ['invoices_module', 'customers_module', 'extra_branch', 'extra_seat']
        if addon_code not in valid_addons:
            raise CommandError(
                f'Código de add-on inválido: {addon_code}\n'
                f'Códigos válidos: {", ".join(valid_addons)}'
            )

        # Verificar si ya existe
        existing = SubscriptionAddon.objects.filter(
            subscription=subscription,
            code=addon_code
        ).first()

        if existing:
            if existing.is_active:
                self.stdout.write(
                    self.style.WARNING(
                        f'⚠️  El add-on "{addon_code}" ya está activo para {business.name}'
                    )
                )
                return
            else:
                # Reactivar
                existing.is_active = True
                existing.quantity = quantity
                existing.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Add-on "{addon_code}" reactivado para {business.name}'
                    )
                )
                return

        # Crear nuevo addon
        addon = SubscriptionAddon.objects.create(
            subscription=subscription,
            code=addon_code,
            quantity=quantity,
            is_active=True
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Add-on "{addon_code}" habilitado exitosamente para {business.name}\n'
                f'   Plan actual: {subscription.plan}\n'
                f'   Cantidad: {quantity}'
            )
        )
