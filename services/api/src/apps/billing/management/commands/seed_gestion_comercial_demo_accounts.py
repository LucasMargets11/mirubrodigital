"""
Management command to seed demo accounts for Gestión Comercial plans testing.

Creates 3 demo users, businesses and subscriptions (one per plan: Start, Pro, Business).
This command is idempotent and only runs in DEBUG mode or local/dev environment.

Usage:
    python manage.py seed_gestion_comercial_demo_accounts
    docker compose exec api python manage.py seed_gestion_comercial_demo_accounts
"""

from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.billing.models import Bundle, Subscription as BillingSubscription
from apps.business.models import Business, Subscription as BusinessSubscription, BusinessPlan
from apps.accounts.models import Membership


User = get_user_model()


class Command(BaseCommand):
    help = 'Seeds 3 demo accounts for testing Gestión Comercial plans (idempotent, DEBUG only)'

    def handle(self, *args, **kwargs):
        # Guard: only in DEBUG or explicit dev environment
        if not settings.DEBUG:
            raise CommandError(
                "❌ Este comando solo se puede ejecutar en DEBUG=True o entorno local/dev. "
                "Rechazado por seguridad."
            )

        self.stdout.write(self.style.WARNING("🔍 Iniciando seed de cuentas demo de Gestión Comercial..."))
        
        try:
            with transaction.atomic():
                bundles = self._discover_gestion_comercial_bundles()
                accounts = self._create_demo_accounts(bundles)
                self._verify_enabled_services(accounts)
                self._print_summary(accounts)
                
            self.stdout.write(self.style.SUCCESS("\n✅ Seed completado exitosamente."))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Error durante el seed: {str(e)}"))
            raise

    def _discover_gestion_comercial_bundles(self):
        """
        Auto-detecta los 3 planes de Gestión Comercial por vertical='commercial'.
        Los ordena por precio mensual (de menor a mayor).
        Valida que haya exactamente 3.
        """
        self.stdout.write("🔍 Detectando planes de Gestión Comercial...")
        
        bundles = Bundle.objects.filter(
            vertical='commercial',
            is_active=True
        ).order_by('fixed_price_monthly')
        
        bundle_list = list(bundles)
        
        if len(bundle_list) < 3:
            raise CommandError(
                f"❌ Se esperaban 3 bundles de Gestión Comercial, pero solo se encontraron {len(bundle_list)}. "
                f"Ejecuta primero: python manage.py seed_billing"
            )
        
        if len(bundle_list) > 3:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️  Se encontraron {len(bundle_list)} bundles. Tomando los 3 principales por precio."
                )
            )
            bundle_list = bundle_list[:3]
        
        for idx, bundle in enumerate(bundle_list, 1):
            price = bundle.fixed_price_monthly / 100 if bundle.fixed_price_monthly else 0
            self.stdout.write(f"   {idx}. {bundle.name} ({bundle.code}) - ${price:.2f}/mes")
        
        return bundle_list

    def _create_demo_accounts(self, bundles):
        """
        Crea (o actualiza) 3 usuarios, negocios y suscripciones.
        Retorna una lista de diccionarios con la info de cada cuenta.
        """
        # Mapeo de bundles a planes legacy
        bundle_to_legacy_plan = {
            'gestion_start': BusinessPlan.START,
            'gestion_pro': BusinessPlan.PRO,
            'gestion_business': BusinessPlan.BUSINESS,
        }
        
        demo_data = [
            {
                'email': 'gc.basic@demo.local',
                'username': 'gc_basic_demo',
                'business_name': 'GC Basic Demo',
                'bundle': bundles[0],  # Plan más barato (Start)
            },
            {
                'email': 'gc.pro@demo.local',
                'username': 'gc_pro_demo',
                'business_name': 'GC Pro Demo',
                'bundle': bundles[1],  # Plan medio (Pro)
            },
            {
                'email': 'gc.max@demo.local',
                'username': 'gc_max_demo',
                'business_name': 'GC Max Demo',
                'bundle': bundles[2],  # Plan más caro (Business)
            },
        ]
        
        password = 'Demo12345!'
        accounts = []
        
        for data in demo_data:
            self.stdout.write(f"\n📦 Procesando: {data['email']}...")
            
            # 1. Crear/obtener usuario
            user, created = User.objects.get_or_create(
                email=data['email'],
                defaults={
                    'username': data['username'],
                    'is_active': True,
                    'is_staff': False,
                }
            )
            
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(f"   ✅ Usuario creado: {user.email}")
            else:
                # Actualizar password por si acaso
                user.set_password(password)
                user.save()
                self.stdout.write(f"   ♻️  Usuario ya existía: {user.email} (password actualizado)")
            
            # 2. Crear/obtener negocio
            business, created = Business.objects.get_or_create(
                name=data['business_name'],
                defaults={
                    'default_service': 'gestion',
                    'status': 'active',
                    'parent': None,  # Es HQ, no branch
                }
            )
            
            if created:
                self.stdout.write(f"   ✅ Negocio creado: {business.name}")
            else:
                self.stdout.write(f"   ♻️  Negocio ya existía: {business.name}")
            
            # 3. Crear/actualizar Membership (relación user-business)
            membership, m_created = Membership.objects.get_or_create(
                user=user,
                business=business,
                defaults={'role': 'owner'}
            )
            
            if m_created:
                self.stdout.write(f"   ✅ Membership creado: {user.email} → {business.name} (owner)")
            else:
                # Asegurar que el rol sea owner
                if membership.role != 'owner':
                    membership.role = 'owner'
                    membership.save()
                    self.stdout.write(f"   ♻️  Membership actualizado a owner")
                else:
                    self.stdout.write(f"   ℹ️  Membership ya existía")
            
            # 4. Crear/actualizar BusinessSubscription (sistema legacy)
            legacy_plan = bundle_to_legacy_plan.get(data['bundle'].code, BusinessPlan.START)
            
            # Determinar límites según el plan
            limits_by_plan = {
                BusinessPlan.START: {'max_branches': 1, 'max_seats': 2},
                BusinessPlan.PRO: {'max_branches': 1, 'max_seats': 10},
                BusinessPlan.BUSINESS: {'max_branches': 5, 'max_seats': 20},
            }
            limits = limits_by_plan.get(legacy_plan, {'max_branches': 1, 'max_seats': 2})
            
            business_sub, bs_created = BusinessSubscription.objects.update_or_create(
                business=business,
                defaults={
                    'plan': legacy_plan,
                    'service': 'gestion',
                    'status': 'active',
                    'max_branches': limits['max_branches'],
                    'max_seats': limits['max_seats'],
                    'renews_at': None,
                }
            )
            
            if bs_created:
                self.stdout.write(f"   ✅ Suscripción legacy creada: {legacy_plan}")
            else:
                self.stdout.write(f"   ♻️  Suscripción legacy actualizada: {legacy_plan}")
            
            # 5. Crear/actualizar BillingSubscription (sistema nuevo)
            billing_sub, s_created = BillingSubscription.objects.update_or_create(
                business=business,
                defaults={
                    'plan_type': 'bundle',
                    'bundle': data['bundle'],
                    'billing_period': 'monthly',
                    'currency': 'ARS',
                    'status': 'active',
                    'price_snapshot': {
                        'bundle_code': data['bundle'].code,
                        'bundle_name': data['bundle'].name,
                        'price_monthly': str(data['bundle'].fixed_price_monthly),
                        'created_at': timezone.now().isoformat(),
                    },
                    'current_period_end': None,
                    'next_billing_date': None,
                }
            )
            
            # Asociar módulos del bundle
            if data['bundle'].modules.exists():
                billing_sub.selected_modules.set(data['bundle'].modules.all())
            
            if s_created:
                self.stdout.write(
                    f"   ✅ Suscripción billing creada: {data['bundle'].name} (activa)"
                )
            else:
                self.stdout.write(
                    f"   ♻️  Suscripción billing actualizada: {data['bundle'].name} (activa)"
                )
            
            accounts.append({
                'email': data['email'],
                'password': password,
                'business_name': data['business_name'],
                'bundle_name': data['bundle'].name,
                'bundle_code': data['bundle'].code,
                'legacy_plan': legacy_plan,
                'user': user,
                'business': business,
                'subscription': billing_sub,
            })
        
        return accounts

    def _verify_enabled_services(self, accounts):
        """
        Verifica que los servicios estén realmente habilitados usando el mismo resolver que la API.
        Si alguna cuenta no tiene 'gestion' habilitado, el comando falla.
        """
        from apps.business.context import build_business_context
        
        self.stdout.write("\n🔍 Verificando servicios habilitados con el resolver...")
        
        all_ok = True
        for account in accounts:
            business = account['business']
            context = build_business_context(business)
            enabled = context['enabled_services']
            
            if 'gestion' in enabled:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"   ✅ {account['email']}: servicios habilitados = {enabled}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"   ❌ {account['email']}: servicios habilitados = {enabled} (esperaba 'gestion')"
                    )
                )
                all_ok = False
        
        if not all_ok:
            raise CommandError(
                "\n❌ Verificación fallida: algunas cuentas NO tienen Gestión Comercial habilitado. "
                "Revisar configuración de planes en features.py y service_catalog.py"
            )

    def _print_summary(self, accounts):
        """
        Imprime un resumen amigable con las credenciales de acceso.
        """
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("✅ CUENTAS DEMO CREADAS / ACTUALIZADAS"))
        self.stdout.write("=" * 80)
        
        for idx, account in enumerate(accounts, 1):
            price = account['subscription'].bundle.fixed_price_monthly / 100 if account['subscription'].bundle.fixed_price_monthly else 0
            
            self.stdout.write(f"\n{idx}. Plan: {account['bundle_name']} ({account['bundle_code']})")
            self.stdout.write(f"   📧 Email:     {account['email']}")
            self.stdout.write(f"   🔑 Password:  {account['password']}")
            self.stdout.write(f"   🏢 Negocio:   {account['business_name']}")
            self.stdout.write(f"   � Legacy:    {account['legacy_plan']}")
            self.stdout.write(f"   �💰 Precio:    ${price:.2f}/mes")
            self.stdout.write(f"   📦 Módulos:   {account['subscription'].selected_modules.count()} incluidos")
        
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("🔗 Acceso:")
        self.stdout.write("   Frontend:  http://localhost:3000/entrar")
        self.stdout.write("   Admin:     http://localhost:8000/admin")
        self.stdout.write("=" * 80 + "\n")
