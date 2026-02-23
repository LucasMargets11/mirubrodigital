"""
Management command para actualizar el plan de una subscription.

Uso:
    python manage.py upgrade_plan <business_id> <plan_code>

Ejemplos:
    python manage.py upgrade_plan 5 pro
    python manage.py upgrade_plan 5 business
"""
from django.core.management.base import BaseCommand, CommandError
from apps.business.models import Business, BusinessPlan


class Command(BaseCommand):
    help = 'Actualiza el plan de un business'

    def add_arguments(self, parser):
        parser.add_argument('business_id', type=int, help='ID del business')
        parser.add_argument('plan_code', type=str, help='Código del nuevo plan (start, pro, business, enterprise)')

    def handle(self, *args, **options):
        business_id = options['business_id']
        plan_code = options['plan_code'].lower()

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

        # Validar plan
        valid_plans = ['start', 'starter', 'pro', 'business', 'enterprise', 'plus']
        if plan_code not in valid_plans:
            raise CommandError(
                f'Código de plan inválido: {plan_code}\n'
                f'Códigos válidos: {", ".join(valid_plans)}'
            )

        # Mapear legacy plans
        plan_map = {
            'starter': 'start',
            'plus': 'business',
        }
        plan_code = plan_map.get(plan_code, plan_code)

        old_plan = subscription.plan
        subscription.plan = plan_code
        subscription.save(update_fields=['plan'])

        # Mostrar diferencias
        from apps.business.entitlements import get_plan_entitlements
        
        old_entitlements = get_plan_entitlements(old_plan)
        new_entitlements = get_plan_entitlements(plan_code)
        
        added = new_entitlements - old_entitlements
        removed = old_entitlements - new_entitlements

        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Plan actualizado exitosamente para {business.name}\n'
                f'   Plan anterior: {old_plan.upper()}\n'
                f'   Plan nuevo: {plan_code.upper()}'
            )
        )

        if added:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n📦 Funcionalidades agregadas:\n   - ' + '\n   - '.join(sorted(added))
                )
            )

        if removed:
            self.stdout.write(
                self.style.WARNING(
                    f'\n⚠️  Funcionalidades removidas:\n   - ' + '\n   - '.join(sorted(removed))
                )
            )

        # Mostrar addons activos
        addons = subscription.addons.filter(is_active=True)
        if addons.exists():
            self.stdout.write(
                self.style.NOTICE(
                    f'\n🔌 Add-ons activos:'
                )
            )
            for addon in addons:
                self.stdout.write(f'   - {addon.code} (qty: {addon.quantity})')
