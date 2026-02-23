"""
Script para verificar products_count en categorías
"""
import django
import os
import sys

sys.path.insert(0, '/app/src')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
import json

User = get_user_model()

def test_products_count():
    print("\n" + "="*80)
    print("TEST: products_count en Categorías")
    print("="*80 + "\n")
    
    user = User.objects.get(email='gc.pro@demo.local')
    membership = user.memberships.first()
    business_id = str(membership.business_id)
    
    client = APIClient()
    client.force_authenticate(user=user)
    
    # GET categorías con products_count
    print("1️⃣ GET /api/v1/catalog/categories/ (verificando products_count)")
    response = client.get('/api/v1/catalog/categories/', HTTP_X_BUSINESS_ID=business_id, HTTP_HOST='localhost')
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        categories = response.json()
        print(f"   Categorías encontradas: {len(categories)}\n")
        
        for cat in categories:
            print(f"   📦 {cat['name']}")
            print(f"      - ID: {cat['id'][:8]}...")
            print(f"      - Activa: {cat['is_active']}")
            print(f"      - Productos: {cat.get('products_count', 'NO DISPONIBLE')}")
            
            if 'products_count' not in cat:
                print(f"      ❌ FALTA products_count")
            else:
                print(f"      ✅ products_count presente")
            print()
        
        # Verificar que todas tienen products_count
        all_have_count = all('products_count' in cat for cat in categories)
        if all_have_count:
            print("✅ TODAS las categorías tienen products_count")
        else:
            print("❌ ALGUNAS categorías NO tienen products_count")
    else:
        print(f"   ❌ Error al obtener categorías: {response.status_code}")
    
    print("\n" + "="*80)
    print("FIN DEL TEST")
    print("="*80 + "\n")

if __name__ == '__main__':
    test_products_count()
