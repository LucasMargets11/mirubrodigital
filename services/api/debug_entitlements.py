"""
Script de diagnóstico para verificar entitlements y subscripciones
"""
import django
import os
import sys

# Setup Django
sys.path.insert(0, '/app/src')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from apps.business.models import Business, Subscription
from apps.business.entitlements import has_entitlement, get_effective_entitlements

User = get_user_model()

def debug_user_entitlements():
    print("\n" + "="*80)
    print("DEBUG: Entitlements y Subscripciones")
    print("="*80 + "\n")
    
    # Listar todos los usuarios que tengan email con 'demo' o sean staff
    users = User.objects.filter(email__icontains='demo').order_by('email')
    
    if not users.exists():
        print("⚠️  No se encontraron usuarios demo. Mostrando todos los usuarios...\n")
        users = User.objects.all().order_by('email')[:5]
    
    for user in users:
        print(f"\n{'='*80}")
        print(f"👤 Usuario: {user.email} (ID: {user.id})")
        print(f"{'='*80}")
        
        memberships = user.memberships.select_related('business', 'business__subscription').all()
        
        if not memberships.exists():
            print("   ❌ No tiene memberships (no pertenece a ningún negocio)")
            continue
        
        for membership in memberships:
            business = membership.business
            print(f"\n   🏢 Negocio: {business.name} (ID: {business.id})")
            print(f"   📋 Role: {membership.role}")
            print(f"   🔧 Servicio: {business.default_service}")
            
            try:
                subscription = business.subscription
                print(f"\n   💳 Suscripción:")
                print(f"      - Plan: {subscription.plan}")
                print(f"      - Status: {subscription.status}")
                print(f"      - Service: {subscription.service}")
                
                # Verificar entitlements efectivos
                entitlements = get_effective_entitlements(subscription)
                print(f"\n   🎫 Entitlements ({len(entitlements)}):")
                for ent in sorted(entitlements):
                    print(f"      ✓ {ent}")
                
                # Verificar entitlements específicos
                print(f"\n   🔍 Verificación de accesos clave:")
                key_entitlements = [
                    'gestion.cash',
                    'gestion.customers',
                    'gestion.invoices',
                    'gestion.reports',
                    'gestion.products',
                ]
                for ent in key_entitlements:
                    has_it = has_entitlement(business, ent)
                    icon = "✅" if has_it else "❌"
                    print(f"      {icon} {ent}")
                    
            except Subscription.DoesNotExist:
                print(f"\n   ❌ NO TIENE SUSCRIPCIÓN")
            except Exception as e:
                print(f"\n   ⚠️  Error al obtener suscripción: {e}")
    
    print("\n" + "="*80 + "\n")

if __name__ == '__main__':
    debug_user_entitlements()
