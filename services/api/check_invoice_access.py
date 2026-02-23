#!/usr/bin/env python
"""
Script para diagnosticar acceso a facturas.
Uso: python check_invoice_access.py <business_id>
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.config.settings')
django.setup()

from apps.business.models import Business, Subscription
from apps.business.entitlements import has_entitlement, get_effective_entitlements
from apps.accounts.models import Membership
from apps.accounts.rbac import permissions_for_service


def check_business_invoice_access(business_id: int):
    """Verifica el acceso a facturas de un negocio."""
    try:
        business = Business.objects.select_related('subscription').get(id=business_id)
    except Business.DoesNotExist:
        print(f"❌ Negocio {business_id} no encontrado")
        return

    print(f"\n{'='*60}")
    print(f"DIAGNÓSTICO: {business.name} (ID: {business.id})")
    print(f"{'='*60}\n")

    # 1. Verificar subscription
    try:
        subscription = business.subscription
        print(f"📋 PLAN ACTUAL:")
        print(f"   - Plan: {subscription.plan}")
        print(f"   - Estado: {subscription.status}")
        print(f"   - Servicio: {subscription.service}")
    except Exception as e:
        print(f"❌ Error obteniendo subscription: {e}")
        return

    # 2. Verificar entitlements
    print(f"\n🎯 ENTITLEMENTS:")
    entitlements = get_effective_entitlements(subscription)
    has_invoices = has_entitlement(business, 'gestion.invoices')
    
    if has_invoices:
        print(f"   ✅ gestion.invoices: SÍ")
    else:
        print(f"   ❌ gestion.invoices: NO")
        print(f"\n   💡 SOLUCIÓN:")
        print(f"      - Actualizar a plan PRO, BUSINESS o ENTERPRISE, O")
        print(f"      - Activar el addon 'invoices_module' (disponible en START)")

    # 3. Verificar add-ons
    print(f"\n🔌 ADD-ONS ACTIVOS:")
    try:
        addons = subscription.addons.filter(is_active=True)
        if addons.exists():
            for addon in addons:
                print(f"   - {addon.code} (qty: {addon.quantity})")
        else:
            print(f"   (ninguno)")
    except Exception:
        print(f"   (no disponible)")

    # 4. Verificar permisos de usuarios
    print(f"\n👥 USUARIOS Y PERMISOS:")
    memberships = Membership.objects.filter(business=business).select_related('user')
    for membership in memberships:
        permissions = permissions_for_service('gestion', membership.role)
        can_issue = permissions.get('issue_invoices', False)
        icon = '✅' if can_issue else '❌'
        print(f"   {icon} {membership.user.email} ({membership.role}) - issue_invoices: {can_issue}")

    # 5. Resumen
    print(f"\n{'='*60}")
    print(f"RESUMEN:")
    print(f"{'='*60}")
    if not has_invoices:
        print(f"❌ El negocio NO puede emitir facturas")
        print(f"\n🔧 PARA HABILITAR FACTURAS:")
        print(f"   1. Actualizar el plan a PRO, BUSINESS o ENTERPRISE:")
        print(f"      Subscription.objects.filter(business_id={business_id}).update(plan='pro')")
        print(f"\n   2. O activar el add-on de facturas (disponible en START):")
        print(f"      from apps.business.models import SubscriptionAddon")
        print(f"      SubscriptionAddon.objects.create(")
        print(f"          subscription_id=subscription.id,")
        print(f"          code='invoices_module',")
        print(f"          quantity=1,")
        print(f"          is_active=True")
        print(f"      )")
    else:
        print(f"✅ El negocio PUEDE emitir facturas")
        print(f"   Si aún hay errores 403, verificar:")
        print(f"   - Que el usuario tenga el permiso 'issue_invoices'")
        print(f"   - Que la subscription esté activa")

    print(f"\n")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Uso: python check_invoice_access.py <business_id>")
        sys.exit(1)
    
    try:
        business_id = int(sys.argv[1])
        check_business_invoice_access(business_id)
    except ValueError:
        print("Error: business_id debe ser un número entero")
        sys.exit(1)
