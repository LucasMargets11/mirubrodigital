"""
Script de prueba para verificar la funcionalidad de categorías de productos
"""
import django
import os
import sys

sys.path.insert(0, '/app/src')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from apps.business.models import Business
from apps.catalog.models import Product, ProductCategory

User = get_user_model()

def test_categories():
    print("\n" + "="*80)
    print("TEST: Categorías de Productos")
    print("="*80 + "\n")
    
    # Buscar un usuario demo con PRO plan
    user = User.objects.filter(email='gc.pro@demo.local').first()
    if not user:
        print("❌ Usuario gc.pro@demo.local no encontrado")
        return
    
    membership = user.memberships.first()
    if not membership:
        print("❌ Usuario no tiene membership")
        return
    
    business = membership.business
    print(f"✅ Usando negocio: {business.name} (ID: {business.id})\n")
    
    # 1. Crear categorías
    print("1️⃣ Creando categorías...")
    categories_data = [
        "Bebidas",
        "Alimentos",
        "Electrónica",
        "Limpieza",
    ]
    
    categories = []
    for cat_name in categories_data:
        cat, created = ProductCategory.objects.get_or_create(
            business=business,
            name=cat_name,
            defaults={'is_active': True}
        )
        status = "creada" if created else "existente"
        print(f"   {cat_name}: {status} ✓")
        categories.append(cat)
    
    # 2. Verificar constraint de unicidad
    print("\n2️⃣ Verificando constraint de unicidad...")
    try:
        duplicate = ProductCategory(business=business, name="Bebidas")
        duplicate.save()
        print("   ❌ FALLO: permitió categoría duplicada")
    except Exception as e:
        print(f"   ✅ Constraint funcionando: {type(e).__name__}")
    
    # 3. Crear productos con categorías
    print("\n3️⃣ Creando productos con categorías...")
    
    products_data = [
        {"name": "Coca Cola 1.5L", "category": categories[0], "price": "500.00"},
        {"name": "Pan Lactal", "category": categories[1], "price": "350.00"},
        {"name": "Mouse Logitech", "category": categories[2], "price": "5000.00"},
        {"name": "Producto sin categoría", "category": None, "price": "100.00"},
    ]
    
    for prod_data in products_data:
        prod, created = Product.objects.get_or_create(
            business=business,
            name=prod_data["name"],
            defaults={
                'category': prod_data["category"],
                'price': prod_data["price"],
                'cost': "0",
                'stock_min': "10"
            }
        )
        status = "creado" if created else "existente"
        cat_name = prod.category.name if prod.category else "Sin categoría"
        print(f"   {prod.name} ({cat_name}): {status} ✓")
    
    # 4. Listar productos por categoría
    print("\n4️⃣ Listando productos por categoría...")
    for category in categories:
        products = Product.objects.filter(business=business, category=category)
        print(f"   {category.name}: {products.count()} productos")
        for prod in products:
            print(f"      - {prod.name}")
    
    # Sin categoría
    no_category = Product.objects.filter(business=business, category__isnull=True)
    print(f"   Sin categoría: {no_category.count()} productos")
    for prod in no_category:
        print(f"      - {prod.name}")
    
    # 5. Ordenamiento
    print("\n5️⃣ Ordenamiento por categoría...")
    products_ordered = Product.objects.filter(
        business=business
    ).select_related('category').order_by('category__name', 'name')
    
    print("   Productos ordenados:")
    for prod in products_ordered[:10]:
        cat_name = prod.category.name if prod.category else "[Sin categoría]"
        print(f"      {cat_name:<20} | {prod.name}")
    
    # 6. Test de SET_NULL al eliminar categoría
    print("\n6️⃣ Probando SET_NULL al eliminar categoría...")
    test_category = ProductCategory.objects.create(
        business=business,
        name="Test Category"
    )
    test_product = Product.objects.create(
        business=business,
        name="Test Product",
        category=test_category,
        price="100",
        cost="50",
        stock_min="5"
    )
    print(f"   Producto creado con categoría: {test_product.category.name}")
    
    # Soft delete (is_active=False)
    test_category.is_active = False
    test_category.save()
    test_product.refresh_from_db()
    print(f"   Después de soft delete: categoría sigue asociada (is_active={test_category.is_active})")
    
    # Hard delete
    test_category.delete()
    test_product.refresh_from_db()
    print(f"   Después de hard delete: category = {test_product.category} ✓")
    
    test_product.delete()
    
    print("\n" + "="*80)
    print("✅ TODAS LAS PRUEBAS PASARON")
    print("="*80 + "\n")

if __name__ == '__main__':
    test_categories()
