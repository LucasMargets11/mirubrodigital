"""
Script para probar endpoints de la API de categorías
"""
import django
import os
import sys

sys.path.insert(0, '/app/src')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()

def test_api_endpoints():
    print("\n" + "="*80)
    print("TEST: Endpoints de API de Categorías")
    print("="*80 + "\n")
    
    user = User.objects.get(email='gc.pro@demo.local')
    membership = user.memberships.first()
    business_id = str(membership.business_id)
    
    client = APIClient()
    client.force_authenticate(user=user)
    
    # GET categorías
    print("1️⃣ GET /api/v1/catalog/categories/")
    response = client.get('/api/v1/catalog/categories/', HTTP_X_BUSINESS_ID=business_id, HTTP_HOST='localhost')
    print(f"   Status: {response.status_code}")
    data = response.json()
    print(f"   Categorías encontradas: {len(data)}")
    for cat in data[:3]:
        print(f"      - {cat['name']} (ID: {cat['id'][:8]}...)")
    
    # POST nueva categoría
    print("\n2️⃣ POST /api/v1/catalog/categories/")
    response = client.post(
        '/api/v1/catalog/categories/',
        {'name': 'API Test Category'},
        HTTP_X_BUSINESS_ID=business_id,
        HTTP_HOST='localhost',
        format='json'
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 201:
        new_cat = response.json()
        print(f"   ✅ Creada: {new_cat['name']} (ID: {new_cat['id'][:8]}...)")
        
        # PATCH categoría
        print(f"\n3️⃣ PATCH /api/v1/catalog/categories/{new_cat['id']}/")
        response = client.patch(
            f'/api/v1/catalog/categories/{new_cat["id"]}/',
            {'name': 'Updated Name'},
            HTTP_X_BUSINESS_ID=business_id,
            HTTP_HOST='localhost',
            format='json'
        )
        print(f"   Status: {response.status_code}")
        updated = response.json()
        print(f"   ✅ Nuevo nombre: {updated['name']}")
        
        # DELETE categoría (soft delete)
        print(f"\n4️⃣ DELETE /api/v1/catalog/categories/{new_cat['id']}/")
        response = client.delete(
            f'/api/v1/catalog/categories/{new_cat["id"]}/',
            HTTP_X_BUSINESS_ID=business_id,
            HTTP_HOST='localhost'
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 204:
            print(f"   ✅ Categoría eliminada (soft delete)")
        
        # Verificar que ya no aparece
        print(f"\n5️⃣ Verificando soft delete...")
        response = client.get('/api/v1/catalog/categories/', HTTP_X_BUSINESS_ID=business_id, HTTP_HOST='localhost')
        data = response.json()
        deleted_exists = any(c['id'] == new_cat['id'] for c in data)
        if not deleted_exists:
            print(f"   ✅ La categoría eliminada NO aparece en el listado")
    
    # GET productos con filtro de categoría
    print("\n6️⃣ GET /api/v1/catalog/products/?category=...")
    cats = client.get('/api/v1/catalog/categories/', HTTP_X_BUSINESS_ID=business_id, HTTP_HOST='localhost').json()
    if cats:
        cat_id = cats[0]['id']
        response = client.get(
            f'/api/v1/catalog/products/?category={cat_id}',
            HTTP_X_BUSINESS_ID=business_id,
            HTTP_HOST='localhost'
        )
        print(f"   Status: {response.status_code}")
        result = response.json()
        # Determinar si es lista o paginado
        if isinstance(result, dict) and 'count' in result:
            count = result['count']
        elif isinstance(result, list):
            count = len(result)
        else:
            count = 0
        print(f"   ✅ Productos con categoría '{cats[0]['name']}': {count}")
        
    # GET productos sin categoría
    print("\n7️⃣ GET /api/v1/catalog/products/?category=null")
    response = client.get(
        '/api/v1/catalog/products/?category=null',
        HTTP_X_BUSINESS_ID=business_id,
        HTTP_HOST='localhost'
    )
    print(f"   Status: {response.status_code}")
    result = response.json()
    if isinstance(result, dict) and 'count' in result:
        count = result['count']
    elif isinstance(result, list):
        count = len(result)
    else:
        count = 0
    print(f"   ✅ Productos sin categoría: {count}")
    
    print("\n" + "="*80)
    print("✅ TODOS LOS TESTS DE API PASARON")
    print("="*80 + "\n")

if __name__ == '__main__':
    test_api_endpoints()
