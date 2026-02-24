"""
Management command to seed comprehensive test data for all 3 GC demo accounts.

Creates large amounts of realistic test data covering ALL features of each plan:
  - START  : Products, Stock movements, Basic Sales
  - PRO    : + Customers, Cash Registers/Sessions, Quotes, Invoices, Treasury
  - BUSINESS: + Branches, rich multi-entity data, Employees/Payroll

Usage:
    python manage.py seed_gestion_comercial_test_data
    docker compose exec api python manage.py seed_gestion_comercial_test_data

Idempotent: skips already-seeded sections. DEBUG=True only.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Membership
from apps.business.models import (
    Business,
    BusinessBillingProfile,
    BusinessPlan,
    CommercialSettings,
    Subscription as BusinessSubscription,
)
from apps.cash.models import CashMovement, CashRegister, CashSession, Payment
from apps.catalog.models import Product, ProductCategory
from apps.customers.models import Customer
from apps.inventory.models import ProductStock, StockMovement
from apps.invoices.models import DocumentSeries, Invoice, InvoiceSeries
from apps.sales.models import Quote, QuoteItem, QuoteSequence, Sale, SaleItem
from apps.treasury.models import (
    Account as TreasuryAccount,
    Employee,
    Expense,
    FixedExpense,
    FixedExpensePeriod,
    PayrollPayment,
    Transaction as TreasuryTransaction,
    TransactionCategory as TreasuryCategory,
    TreasurySettings,
)

User = get_user_model()

# ─────────────────────────────────────────────────────────────────────────────
# DATA CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

TODAY = date.today()
NOW = timezone.now()

# 15 customers for PRO plan
PRO_CUSTOMERS = [
    {"name": "María García", "type": "individual", "doc_type": "dni", "doc_number": "28541236",
     "email": "maria.garcia@email.com", "phone": "11-4523-6789", "city": "Buenos Aires",
     "tax_condition": "consumer"},
    {"name": "Carlos López", "type": "individual", "doc_type": "dni", "doc_number": "32198741",
     "email": "carlos.lopez@email.com", "phone": "351-456-7890", "city": "Córdoba",
     "tax_condition": "consumer"},
    {"name": "Distribuidora Norte SA", "type": "company", "doc_type": "cuit", "doc_number": "30-71234567-9",
     "email": "compras@distribnorte.com.ar", "phone": "11-4000-1234", "city": "Buenos Aires",
     "tax_condition": "registered"},
    {"name": "Ana Rodríguez", "type": "individual", "doc_type": "dni", "doc_number": "25874136",
     "email": "ana.rodriguez@gmail.com", "phone": "261-890-1234", "city": "Mendoza",
     "tax_condition": "consumer"},
    {"name": "TecnoSur SRL", "type": "company", "doc_type": "cuit", "doc_number": "30-65432198-3",
     "email": "admin@tecnosur.com", "phone": "11-4567-8901", "city": "La Plata",
     "tax_condition": "registered"},
    {"name": "Roberto Fernández", "type": "individual", "doc_type": "dni", "doc_number": "18965432",
     "email": "robfernandez@hotmail.com", "phone": "221-234-5678", "city": "La Plata",
     "tax_condition": "consumer"},
    {"name": "Laura Martínez", "type": "individual", "doc_type": "dni", "doc_number": "30145827",
     "email": "laura.mtz@outlook.com", "phone": "11-5678-9012", "city": "Buenos Aires",
     "tax_condition": "monotax"},
    {"name": "Grupo Comercial ABC", "type": "company", "doc_type": "cuit", "doc_number": "33-88888888-9",
     "email": "ventas@grupoabc.com.ar", "phone": "11-4800-0000", "city": "Buenos Aires",
     "tax_condition": "registered"},
    {"name": "Diego Sánchez", "type": "individual", "doc_type": "dni", "doc_number": "27654123",
     "email": "dsanchez@yahoo.com", "phone": "341-789-0123", "city": "Rosario",
     "tax_condition": "consumer"},
    {"name": "Valentina Torres", "type": "individual", "doc_type": "dni", "doc_number": "34789012",
     "email": "val.torres@gmail.com", "phone": "11-6789-0123", "city": "Buenos Aires",
     "tax_condition": "consumer"},
    {"name": "Importadora Del Sur SAS", "type": "company", "doc_type": "cuit", "doc_number": "30-22334455-6",
     "email": "importaciones@delsur.com", "phone": "11-4900-2200", "city": "San Justo",
     "tax_condition": "registered"},
    {"name": "Martín Pérez", "type": "individual", "doc_type": "dni", "doc_number": "22456789",
     "email": "mperez.85@gmail.com", "phone": "11-7890-1234", "city": "Buenos Aires",
     "tax_condition": "monotax"},
    {"name": "Sofía Romero", "type": "individual", "doc_type": "dni", "doc_number": "38901234",
     "email": "sofia.romero@live.com", "phone": "114-456-7890", "city": "CABA",
     "tax_condition": "consumer"},
    {"name": "Electrónica Andina SA", "type": "company", "doc_type": "cuit", "doc_number": "30-55667788-1",
     "email": "compras@andina-elec.com.ar", "phone": "381-222-3333", "city": "San Miguel de Tucumán",
     "tax_condition": "registered"},
    {"name": "Juan Gómez", "type": "individual", "doc_type": "dni", "doc_number": "20987654",
     "email": "jgomez@protonmail.com", "phone": "11-8901-2345", "city": "Lomas de Zamora",
     "tax_condition": "consumer"},
]

# 30 customers for BUSINESS plan (includes PRO_CUSTOMERS + 15 more)
BUSINESS_EXTRA_CUSTOMERS = [
    {"name": "Global Traders SA", "type": "company", "doc_type": "cuit", "doc_number": "30-12345678-9",
     "email": "comercial@globaltraders.com", "phone": "11-4111-2222", "city": "Buenos Aires",
     "tax_condition": "registered"},
    {"name": "Lucía Cabrera", "type": "individual", "doc_type": "dni", "doc_number": "29012345",
     "email": "lucia.cab@gmail.com", "phone": "11-3456-7890", "city": "Quilmes",
     "tax_condition": "consumer"},
    {"name": "MegaDist SRL", "type": "company", "doc_type": "cuit", "doc_number": "33-44556677-8",
     "email": "ventas@megadist.com.ar", "phone": "11-5555-0000", "city": "Avellaneda",
     "tax_condition": "registered"},
    {"name": "Hernán Vargas", "type": "individual", "doc_type": "dni", "doc_number": "24789456",
     "email": "hvargas@icloud.com", "phone": "223-111-2222", "city": "Mar del Plata",
     "tax_condition": "monotax"},
    {"name": "Comercial Patagonia SA", "type": "company", "doc_type": "cuit", "doc_number": "30-77889900-5",
     "email": "info@comercial-patagonia.com", "phone": "299-444-5555", "city": "Neuquén",
     "tax_condition": "registered"},
    {"name": "Patricia Flores", "type": "individual", "doc_type": "dni", "doc_number": "31234567",
     "email": "patflores89@gmail.com", "phone": "11-9012-3456", "city": "Buenos Aires",
     "tax_condition": "consumer"},
    {"name": "Tech Argentina SAS", "type": "company", "doc_type": "cuit", "doc_number": "30-99887766-4",
     "email": "hola@tech-ar.com.ar", "phone": "11-4200-3000", "city": "Palermo",
     "tax_condition": "registered"},
    {"name": "Francisco Acosta", "type": "individual", "doc_type": "dni", "doc_number": "16543210",
     "email": "facosta@yahoo.com.ar", "phone": "351-333-4444", "city": "Córdoba",
     "tax_condition": "consumer"},
    {"name": "Soluciones Integrales SA", "type": "company", "doc_type": "cuit", "doc_number": "30-66554433-7",
     "email": "admin@solintegral.com", "phone": "11-4700-8900", "city": "Microcentro",
     "tax_condition": "registered"},
    {"name": "Natalia Cruz", "type": "individual", "doc_type": "dni", "doc_number": "36892014",
     "email": "nat.cruz@gmail.com", "phone": "11-0123-4567", "city": "San Isidro",
     "tax_condition": "consumer"},
    {"name": "Proveedor Mayorista Norte SA", "type": "company", "doc_type": "cuit", "doc_number": "30-33221100-2",
     "email": "mayorista@pmnorte.com.ar", "phone": "388-666-7777", "city": "San Salvador de Jujuy",
     "tax_condition": "registered"},
    {"name": "Sebastián Jiménez", "type": "individual", "doc_type": "dni", "doc_number": "33401289",
     "email": "sjimenez94@gmail.com", "phone": "11-2345-6789", "city": "Buenos Aires",
     "tax_condition": "consumer"},
    {"name": "Industrias Del Litoral SRL", "type": "company", "doc_type": "cuit", "doc_number": "30-10293847-6",
     "email": "compras@ind-litoral.com", "phone": "343-222-1111", "city": "Paraná",
     "tax_condition": "registered"},
    {"name": "Camila Herrera", "type": "individual", "doc_type": "dni", "doc_number": "40123456",
     "email": "cami.herrera@live.com.ar", "phone": "11-3210-9876", "city": "Buenos Aires",
     "tax_condition": "consumer"},
    {"name": "InnovaTech Corp SA", "type": "company", "doc_type": "cuit", "doc_number": "30-48596071-3",
     "email": "ventas@innovatech-ar.com", "phone": "11-4600-7700", "city": "Palermo Soho",
     "tax_condition": "registered"},
]

# Product data by plan
START_PRODUCTS = [
    # (name, sku, category_idx, cost, price, stock)
    ("Auriculares Bluetooth BT100", "AUR-BT100", 0, 3500, 5990, 45),
    ("Cable USB-C 2m", "CAB-USBC2M", 0, 350, 890, 120),
    ("Parlante Inalámbrico Mini", "PAR-MINI01", 0, 4200, 7500, 30),
    ("Mouse Inalámbrico", "MOU-INL01", 0, 1500, 2990, 60),
    ("Teclado USB Compacto", "TEC-USB01", 0, 2100, 3990, 40),
    ("Hub USB 4 puertos", "HUB-USB4P", 0, 800, 1590, 80),
    ("Remera Básica Algodón M", "REM-BAS-M", 1, 1200, 2490, 150),
    ("Remera Básica Algodón L", "REM-BAS-L", 1, 1200, 2490, 120),
    ("Pantalón Jean Clásico 32", "PAN-JEA32", 1, 4500, 8990, 50),
    ("Pantalón Jean Clásico 34", "PAN-JEA34", 1, 4500, 8990, 45),
    ("Campera Impermeable", "CAM-IMP01", 1, 5500, 10990, 30),
    ("Zapatillas Running Talle 40", "ZAP-RUN40", 2, 7500, 14990, 25),
    ("Zapatillas Running Talle 42", "ZAP-RUN42", 2, 7500, 14990, 30),
    ("Bota de Cuero Talle 41", "BOT-CUE41", 2, 9000, 18990, 20),
    ("Ojotas Verano", "OJO-VER01", 2, 800, 1990, 80),
    ("Cinturón Cuero Negro", "CIN-CUE01", 3, 1500, 2990, 60),
    ("Billetera Cuero Marrón", "BIL-CUE01", 3, 2000, 3990, 50),
    ("Gorra Deportiva", "GOR-DEP01", 3, 700, 1590, 90),
    ("Reloj Digital Negro", "REL-DIG01", 3, 3500, 6990, 35),
    ("Marco Foto 20x30", "MAR-FO01", 4, 500, 1190, 100),
    ("Veladora Aromática Set x3", "VEL-ARO01", 4, 900, 1990, 70),
    ("Portarretratos Madera", "POR-MAD01", 4, 750, 1490, 85),
    ("Funda Almohada 50x70", "FUN-ALM01", 4, 600, 1290, 120),
    ("Set Vasos x6 Vidrio", "VAR-VID01", 4, 1800, 3490, 40),
    ("Agua Mineral 2L", "AGU-MIN2L", 5, 120, 290, 200),
    ("Gaseosa Cola 2L", "GAS-COL2L", 5, 180, 390, 180),
    ("Chips Papas Set x10", "CHI-PAP01", 5, 400, 890, 150),
    ("Café Molido 250g", "CAF-MOL01", 5, 700, 1490, 90),
    ("Galletitas Surtidas x6", "GAL-SUR01", 5, 550, 1190, 110),
    ("Chocolate Tableta x3", "CHO-TAB01", 5, 450, 990, 130),
]

PRO_PRODUCTS = [
    ("Notebook ASUS 15\" i5", "NOT-ASU-i5", 0, 280000, 459990, 15),
    ("Notebook HP 14\" i3", "NOT-HP-i3", 0, 210000, 349990, 18),
    ("Monitor 24\" Full HD", "MON-24FHD", 0, 95000, 159990, 22),
    ("Teclado Mecánico RGB", "TEC-MEC01", 0, 18000, 32990, 30),
    ("Mouse Gamer 6000 DPI", "MOU-GAM01", 0, 12000, 21990, 35),
    ("Disco SSD 480GB", "SSD-480GB", 0, 35000, 58990, 40),
    ("Memoria RAM 8GB DDR4", "RAM-8GB01", 0, 18500, 31990, 45),
    ("Fuente 600W 80+", "FUE-600W", 0, 28000, 48990, 20),
    ("Smartphone Samsung A55", "TEL-SAM55", 1, 190000, 329990, 20),
    ("Smartphone Xiaomi 13T", "TEL-XIA13", 1, 160000, 279990, 25),
    ("Funda Celular Universal", "FUN-CEL01", 1, 800, 1990, 150),
    ("Protector de Pantalla Universal", "PRO-PAN01", 1, 600, 1490, 200),
    ("Cargador Rápido 65W USB-C", "CAR-65W01", 1, 5500, 9990, 80),
    ("Power Bank 20000mAh", "POW-20K01", 1, 15000, 26990, 50),
    ("Auriculares In-Ear Noise Cancel", "AUR-NC01", 2, 45000, 79990, 30),
    ("Parlante Bluetooth 30W JBL", "PAR-JBL30", 2, 38000, 64990, 25),
    ("Barra de Sonido 2.1", "BAR-SON01", 2, 65000, 109990, 15),
    ("Smart TV 50\" 4K Android", "STV-50-4K", 2, 210000, 359990, 10),
    ("Proyector Portátil Full HD", "PRO-POT01", 2, 95000, 164990, 8),
    ("Cajas de Energía UPS 600VA", "UPS-600VA", 0, 28000, 49990, 18),
    ("Herramienta Multiusos Pro", "HER-MUL01", 3, 8500, 15990, 40),
    ("Set Llaves Combinadas x12", "LLA-COM12", 3, 5500, 10990, 50),
    ("Taladro Percutor 550W", "TAL-PER01", 3, 42000, 74990, 20),
    ("Manguera 15m Reforzada", "MAN-15M01", 4, 3500, 6990, 35),
    ("Tijera de Podar Profesional", "TIJ-POD01", 4, 3800, 7490, 22),
    ("Maceta Plástica 30cm", "MAC-PLA30", 4, 700, 1590, 100),
    ("Carpeta A4 con Logo", "CAR-A4-01", 5, 350, 890, 200),
    ("Resma A4 500 hojas Premium", "RES-A4-01", 5, 1400, 2990, 120),
    ("Lapicera Pilot G2 x12", "LAP-PIL12", 5, 900, 1990, 180),
    ("Cinta Scotch x10 Rollos", "CIN-SCO10", 5, 800, 1790, 140),
    ("Zapatillas Nike Air talle 42", "ZAP-NIK42", 6, 28000, 49990, 25),
    ("Mochila Deportiva 30L", "MOC-DEP30", 6, 12000, 22990, 35),
    ("Pelota Fútbol N5 Premium", "PEL-FUT01", 6, 7500, 14990, 45),
    ("Camiseta Fútbol Oficial", "CAM-FUT01", 6, 9000, 18990, 60),
    ("Botella Hidratación 1L", "BOT-HID1L", 6, 2200, 4990, 80),
    ("Shampoo Industrial 1L", "SHA-IND1L", 7, 1500, 3490, 90),
    ("Desinfectante 5L Concentrado", "DES-5L01", 7, 2800, 5990, 70),
    ("Guantes Nitrilo x100", "GUA-NIT01", 7, 3500, 6990, 60),
    ("Papel Higiénico x24", "PAP-HIG24", 7, 1800, 3990, 100),
    ("Lavandina 4L Reforzada", "LAV-4L01", 7, 1200, 2790, 85),
    ("Desodorante Ambiente x12", "DES-AMB12", 7, 2400, 4990, 70),
    ("Alfombra de Escritorio Gaming", "ALF-ESC01", 0, 3500, 6990, 40),
    ("Silla Gamer Ergonómica", "SIL-GAM01", 0, 85000, 149990, 12),
    ("Webcam 1080p con Micrófono", "WEB-1080", 0, 22000, 39990, 25),
    ("Router WiFi 6 AX3000", "ROU-AX3K", 0, 55000, 94990, 18),
    ("Switch 8 puertos Gigabit", "SWI-8GB01", 0, 18000, 32990, 22),
    ("Impresora Multifunción Inkjet", "IMP-INK01", 0, 65000, 114990, 12),
    ("Tóner HP Compatible Q2612A", "TON-HP12A", 0, 8500, 16990, 45),
    ("Disco Duro Externo 1TB USB3", "HDD-1TB01", 0, 35000, 59990, 30),
    ("Pendrive 64GB USB 3.0 x5", "PEN-64G5X", 0, 8000, 14990, 60),
    ("Cable HDMI 2.0 2m", "CAB-HDMI2", 0, 1800, 3990, 100),
]

BUSINESS_EXTRA_PRODUCTS = [
    ("Aire Acondicionado 3000 Frig", "AAC-3000F", 0, 280000, 489990, 8),
    ("Lavarropas Automático 7kg", "LAV-7KG01", 0, 195000, 339990, 10),
    ("Heladera con Freezer 320L", "HEL-320L", 0, 250000, 429990, 6),
    ("Microondas 28L Digital", "MIC-28L01", 0, 85000, 149990, 15),
    ("Aspiradora Ciclónica 2200W", "ASP-CIC01", 0, 75000, 129990, 12),
    ("Licuadora Profesional 1200W", "LIC-PRO01", 0, 32000, 59990, 20),
    ("Cafetera Espresso Automática", "CAF-AUT01", 0, 185000, 324990, 8),
    ("Plancha Ropa Vapor 2600W", "PLA-VAP01", 0, 28000, 52990, 25),
    ("Tablet 10\" Android 64GB", "TAB-10A64", 0, 105000, 184990, 18),
    ("Smartwatch Sport GPS", "SWA-GPS01", 0, 85000, 149990, 22),
    ("Cámara Digital 24Mpx", "CAM-DIG24", 0, 210000, 369990, 8),
    ("Trípode Aluminio Pro", "TRI-ALU01", 0, 18000, 34990, 20),
    ("Impresora 3D FDM 220x220", "IMP-3D01", 0, 195000, 349990, 5),
    ("Kit Herramientas Eléctrico x8", "KIT-HER08", 0, 68000, 119990, 15),
    ("Moto Eléctrica Plegable", "MOT-ELE01", 0, 680000, 1199990, 4),
    ("Bicicleta MTB Aluminio 29", "BIC-MTB29", 0, 380000, 669990, 6),
    ("Mesa de Ping Pong Profesional", "MES-PIN01", 0, 195000, 349990, 4),
    ("Colchón Espuma HR 2 plazas", "COL-ESP2P", 0, 95000, 169990, 10),
    ("Sommier 2 plazas Resortes", "SOM-2P01", 0, 180000, 319990, 6),
    ("Escritorio Madera L 180cm", "ESC-MAD01", 0, 125000, 224990, 8),
]


# ─────────────────────────────────────────────────────────────────────────────
# COMMAND
# ─────────────────────────────────────────────────────────────────────────────


class Command(BaseCommand):
    help = 'Seeds comprehensive test data for all 3 GC demo accounts (idempotent, DEBUG only)'

    def handle(self, *args, **kwargs):
        if not settings.DEBUG:
            raise CommandError(
                "❌ Este comando solo puede ejecutarse con DEBUG=True. Rechazado por seguridad."
            )

        self.stdout.write(self.style.WARNING(
            "\n🌱 Iniciando seed de datos de prueba para Gestión Comercial...\n"
        ))

        try:
            with transaction.atomic():
                self._seed_basic_account()
                self._seed_pro_account()
                self._seed_business_account()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Error: {str(e)}"))
            raise

        self.stdout.write(self.style.SUCCESS("\n✅ Seed de datos de prueba completado exitosamente.\n"))

    # ─────────────────────────────────────────────────────────────────────────
    # PLAN START
    # ─────────────────────────────────────────────────────────────────────────

    def _seed_basic_account(self):
        self.stdout.write("=" * 70)
        self.stdout.write("📦  PLAN START — gc.basic@demo.local")
        self.stdout.write("=" * 70)

        business = self._get_business('GC Basic Demo')
        if not business:
            self.stdout.write(self.style.WARNING("   ⚠️  Negocio no encontrado. Ejecuta seed_gestion_comercial_demo_accounts primero."))
            return

        user = User.objects.filter(email='gc.basic@demo.local').first()
        if not user:
            self.stdout.write(self.style.WARNING("   ⚠️  Usuario no encontrado."))
            return

        # CommercialSettings
        cs, _ = CommercialSettings.objects.get_or_create(business=business)
        cs.allow_sell_without_stock = True
        cs.block_sales_if_no_open_cash_session = False
        cs.require_customer_for_sales = False
        cs.enable_sales_notes = True
        cs.warn_on_low_stock_threshold_enabled = True
        cs.low_stock_threshold_default = 5
        cs.save()
        self.stdout.write("   ✅ CommercialSettings configurado")

        # Billing profile
        self._setup_billing_profile(
            business,
            legal_name="TechShop SRL",
            tax_id="30-71234567-0",
            vat_condition="responsable_inscripto",
            address="Av. Corrientes 1234, CABA",
            email="admin@techshop.com.ar",
            phone="11-4000-1111",
        )

        # Extra staff user (START max_seats=2 → owner + 1)
        staff1 = self._get_or_create_user('gc.basic.staff1@demo.local', 'gc_basic_staff1')
        self._get_or_create_membership(staff1, business, 'staff')
        self.stdout.write("   ✅ Usuario staff adicional: gc.basic.staff1@demo.local")

        # Categories
        cat_names = ['Electrónica', 'Ropa y Moda', 'Calzado', 'Accesorios', 'Hogar y Deco', 'Alimentos y Bebidas']
        categories = self._create_categories(business, cat_names)

        # Products
        products = self._create_products_from_list(business, categories, START_PRODUCTS, user)
        self.stdout.write(f"   ✅ {len(products)} productos en catálogo")

        # Stock
        mv = self._seed_stock_start(business, products, user)
        self.stdout.write(f"   ✅ {mv} movimientos de stock (IN + ADJUST + OUT)")

        # Sales (basic — no cash session)
        sales_count = self._seed_sales_start(business, products, user)
        self.stdout.write(f"   ✅ {sales_count} ventas creadas (sin sesión de caja)")

        self.stdout.write(self.style.SUCCESS("   🎉 Plan START completado\n"))

    # ─────────────────────────────────────────────────────────────────────────
    # PLAN PRO
    # ─────────────────────────────────────────────────────────────────────────

    def _seed_pro_account(self):
        self.stdout.write("=" * 70)
        self.stdout.write("⭐  PLAN PRO — gc.pro@demo.local")
        self.stdout.write("=" * 70)

        business = self._get_business('GC Pro Demo')
        if not business:
            self.stdout.write(self.style.WARNING("   ⚠️  Negocio no encontrado."))
            return

        user = User.objects.filter(email='gc.pro@demo.local').first()
        if not user:
            self.stdout.write(self.style.WARNING("   ⚠️  Usuario no encontrado."))
            return

        # CommercialSettings
        cs, _ = CommercialSettings.objects.get_or_create(business=business)
        cs.allow_sell_without_stock = False
        cs.block_sales_if_no_open_cash_session = False  # false para seeding directo
        cs.require_customer_for_sales = False
        cs.enable_sales_notes = True
        cs.warn_on_low_stock_threshold_enabled = True
        cs.low_stock_threshold_default = 3
        cs.save()

        # Billing profile
        self._setup_billing_profile(
            business,
            legal_name="ProVentas SA",
            tax_id="30-98765432-1",
            vat_condition="responsable_inscripto",
            address="Av. Santa Fe 4500, Buenos Aires",
            email="contabilidad@proventas.com.ar",
            phone="11-4500-2222",
        )

        # Staff users (4 extras, total 5 with owner, max_seats=10)
        staff_data = [
            ('gc.pro.admin@demo.local', 'gc_pro_admin', 'admin'),
            ('gc.pro.manager@demo.local', 'gc_pro_manager', 'manager'),
            ('gc.pro.cashier@demo.local', 'gc_pro_cashier', 'cashier'),
            ('gc.pro.analyst@demo.local', 'gc_pro_analyst', 'analyst'),
        ]
        staff_users = {}
        for email, username, role in staff_data:
            u = self._get_or_create_user(email, username)
            self._get_or_create_membership(u, business, role)
            staff_users[role] = u
        self.stdout.write(f"   ✅ {len(staff_users)} usuarios staff creados/actualizados")

        cashier = staff_users.get('cashier', user)
        manager = staff_users.get('manager', user)

        # Categories
        cat_names = [
            'Computación', 'Telefonía Celular', 'Audio y Video',
            'Ferretería', 'Jardinería', 'Librería y Papelería',
            'Deportes', 'Higiene y Limpieza',
        ]
        categories = self._create_categories(business, cat_names)

        # Products
        products = self._create_products_from_list(business, categories, PRO_PRODUCTS, user)
        self.stdout.write(f"   ✅ {len(products)} productos en catálogo")

        # Stock (rich: IN, OUT, ADJUST)
        mv = self._seed_stock_rich(business, products, user)
        self.stdout.write(f"   ✅ {mv} movimientos de stock")

        # Customers
        customers = self._create_customers(business, PRO_CUSTOMERS)
        self.stdout.write(f"   ✅ {len(customers)} clientes")

        # Cash registers and sessions
        reg1, reg2 = self._create_cash_registers_pro(business)
        # 2 closed sessions + 1 open session
        sess_closed_1 = self._create_cash_session(
            business, reg1, cashier,
            daysago_open=15, daysago_close=15, close_hour=21,
            opening_amount=Decimal('5000'), closing_counted=Decimal('47250'),
        )
        sess_closed_2 = self._create_cash_session(
            business, reg2, cashier,
            daysago_open=8, daysago_close=8, close_hour=22,
            opening_amount=Decimal('3000'), closing_counted=Decimal('38500'),
        )
        sess_open = self._create_cash_session(
            business, reg1, cashier,
            daysago_open=0,
            opening_amount=Decimal('5000'),
        )
        self.stdout.write(f"   ✅ 2 cajas, 3 sesiones (2 cerradas, 1 abierta)")

        # Sales with payments (assigned to sessions)
        sale_count = self._seed_sales_pro(
            business, products, customers, user, cashier,
            [sess_closed_1, sess_closed_2, sess_open]
        )
        self.stdout.write(f"   ✅ {sale_count} ventas con pagos")

        # Cash movements (ingress/egress in sessions)
        self._seed_cash_movements(business, [sess_closed_1, sess_closed_2, sess_open], user)
        self.stdout.write("   ✅ Movimientos de caja extras creados")

        # Quotes
        q_count = self._seed_quotes(business, products, customers, user)
        self.stdout.write(f"   ✅ {q_count} presupuestos (varios estados)")

        # Invoice series + invoices
        inv_count = self._seed_invoices_pro(business, user)
        self.stdout.write(f"   ✅ {inv_count} facturas emitidas")

        # Treasury
        t_info = self._seed_treasury_pro(business, user)
        self.stdout.write(f"   ✅ Treasury: {t_info}")

        self.stdout.write(self.style.SUCCESS("   🎉 Plan PRO completado\n"))

    # ─────────────────────────────────────────────────────────────────────────
    # PLAN BUSINESS
    # ─────────────────────────────────────────────────────────────────────────

    def _seed_business_account(self):
        self.stdout.write("=" * 70)
        self.stdout.write("💼  PLAN BUSINESS — gc.max@demo.local")
        self.stdout.write("=" * 70)

        hq = self._get_business('GC Max Demo')
        if not hq:
            self.stdout.write(self.style.WARNING("   ⚠️  Negocio HQ no encontrado."))
            return

        user = User.objects.filter(email='gc.max@demo.local').first()
        if not user:
            self.stdout.write(self.style.WARNING("   ⚠️  Usuario no encontrado."))
            return

        # CommercialSettings for HQ
        cs, _ = CommercialSettings.objects.get_or_create(business=hq)
        cs.allow_sell_without_stock = False
        cs.block_sales_if_no_open_cash_session = False
        cs.require_customer_for_sales = False
        cs.enable_sales_notes = True
        cs.warn_on_low_stock_threshold_enabled = True
        cs.low_stock_threshold_default = 5
        cs.save()

        self._setup_billing_profile(
            hq,
            legal_name="MaxComercio SA",
            tax_id="30-45678901-2",
            vat_condition="responsable_inscripto",
            address="Paraguay 1500 piso 3, CABA",
            email="finanzas@maxcomercio.com.ar",
            phone="11-4800-0000",
        )

        # 8 staff users (owner + 8 = 9 total, max_seats=20)
        staff_data = [
            ('gc.max.admin@demo.local',   'gc_max_admin',   'admin'),
            ('gc.max.manager@demo.local', 'gc_max_manager', 'manager'),
            ('gc.max.cashier1@demo.local','gc_max_cashier1','cashier'),
            ('gc.max.cashier2@demo.local','gc_max_cashier2','cashier'),
            ('gc.max.analyst@demo.local', 'gc_max_analyst', 'analyst'),
            ('gc.max.staff1@demo.local',  'gc_max_staff1',  'staff'),
            ('gc.max.staff2@demo.local',  'gc_max_staff2',  'staff'),
            ('gc.max.viewer@demo.local',  'gc_max_viewer',  'viewer'),
        ]
        staff_users = {}
        for email, username, role in staff_data:
            u = self._get_or_create_user(email, username)
            self._get_or_create_membership(u, hq, role)
            staff_users[role + '_' + email.split('.')[2]] = u
        self.stdout.write(f"   ✅ {len(staff_users)} usuarios staff creados")

        cashier1 = User.objects.filter(email='gc.max.cashier1@demo.local').first() or user
        cashier2 = User.objects.filter(email='gc.max.cashier2@demo.local').first() or user

        # Branches (Multi-sucursal — BUSINESS feature)
        branch_norte = self._get_or_create_branch(hq, 'GC Max Demo - Sucursal Norte', user, 'Norte')
        branch_sur   = self._get_or_create_branch(hq, 'GC Max Demo - Sucursal Sur',   user, 'Sur')
        self.stdout.write("   ✅ 2 sucursales creadas (Norte, Sur)")

        # Categories (shared catalog concept — each branch gets its own subset)
        cat_names = [
            'Tecnología', 'Electrodomésticos', 'Telefonía',
            'Indumentaria', 'Calzado y Accesorios',
            'Ferretería Pro', 'Deportes y Outdoors',
            'Hogar y Decoración', 'Librería y Oficina', 'Alimentos Gourmet',
        ]
        categories_hq     = self._create_categories(hq, cat_names)
        categories_norte  = self._create_categories(branch_norte, cat_names[:6])
        categories_sur    = self._create_categories(branch_sur,   cat_names[4:9])

        # Products
        all_products_hq = self._create_products_from_list(hq, categories_hq, PRO_PRODUCTS[:30] + BUSINESS_EXTRA_PRODUCTS, user)
        all_products_norte = self._create_products_from_list(branch_norte, categories_norte, START_PRODUCTS[:20], user)
        all_products_sur   = self._create_products_from_list(branch_sur, categories_sur, PRO_PRODUCTS[30:50] + START_PRODUCTS[20:30], user)
        total_prods = len(all_products_hq) + len(all_products_norte) + len(all_products_sur)
        self.stdout.write(f"   ✅ {total_prods} productos (HQ: {len(all_products_hq)}, Norte: {len(all_products_norte)}, Sur: {len(all_products_sur)})")

        # Stock
        mv_hq    = self._seed_stock_rich(hq, all_products_hq, user, factor=2)
        mv_norte = self._seed_stock_rich(branch_norte, all_products_norte, cashier1, factor=1)
        mv_sur   = self._seed_stock_rich(branch_sur,   all_products_sur,   cashier2, factor=1)
        self.stdout.write(f"   ✅ {mv_hq + mv_norte + mv_sur} movimientos de stock totales")

        # Customers
        all_customers_hq    = self._create_customers(hq, PRO_CUSTOMERS + BUSINESS_EXTRA_CUSTOMERS)
        all_customers_norte = self._create_customers(branch_norte, PRO_CUSTOMERS[:10])
        all_customers_sur   = self._create_customers(branch_sur, BUSINESS_EXTRA_CUSTOMERS[:10])
        self.stdout.write(f"   ✅ {len(all_customers_hq) + len(all_customers_norte) + len(all_customers_sur)} clientes totales")

        # Cash registers and sessions
        reg_hq_1 = self._get_or_create_cash_register(hq, 'Caja Principal HQ')
        reg_hq_2 = self._get_or_create_cash_register(hq, 'Caja Secundaria HQ')
        reg_norte = self._get_or_create_cash_register(branch_norte, 'Caja Norte')
        reg_sur   = self._get_or_create_cash_register(branch_sur, 'Caja Sur')

        sess_hq_c1 = self._create_cash_session(hq, reg_hq_1, cashier1, daysago_open=20, daysago_close=20, close_hour=20, opening_amount=Decimal('10000'), closing_counted=Decimal('85000'))
        sess_hq_c2 = self._create_cash_session(hq, reg_hq_2, cashier2, daysago_open=10, daysago_close=10, close_hour=21, opening_amount=Decimal('8000'), closing_counted=Decimal('72500'))
        sess_hq_open = self._create_cash_session(hq, reg_hq_1, cashier1, daysago_open=0, opening_amount=Decimal('10000'))
        sess_norte_c = self._create_cash_session(branch_norte, reg_norte, cashier1, daysago_open=12, daysago_close=12, close_hour=20, opening_amount=Decimal('5000'), closing_counted=Decimal('41000'))
        sess_sur_open = self._create_cash_session(branch_sur, reg_sur, cashier2, daysago_open=0, opening_amount=Decimal('5000'))
        self.stdout.write("   ✅ 4 cajas, 5 sesiones creadas")

        # Sales with payments
        sc_hq    = self._seed_sales_business(hq, all_products_hq, all_customers_hq, user, cashier1, [sess_hq_c1, sess_hq_c2, sess_hq_open], count=30)
        sc_norte = self._seed_sales_business(branch_norte, all_products_norte, all_customers_norte, cashier1, cashier1, [sess_norte_c], count=15)
        sc_sur   = self._seed_sales_business(branch_sur,   all_products_sur,   all_customers_sur,   cashier2, cashier2, [sess_sur_open], count=15)
        self.stdout.write(f"   ✅ {sc_hq + sc_norte + sc_sur} ventas totales con pagos")

        # Cash movements
        self._seed_cash_movements(hq, [sess_hq_c1, sess_hq_c2, sess_hq_open], user, count=6)
        self._seed_cash_movements(branch_norte, [sess_norte_c], cashier1, count=3)
        self.stdout.write("   ✅ Movimientos de caja extras")

        # Quotes
        q_hq    = self._seed_quotes(hq, all_products_hq, all_customers_hq, user, count=12)
        q_norte = self._seed_quotes(branch_norte, all_products_norte, all_customers_norte, cashier1, count=5)
        q_sur   = self._seed_quotes(branch_sur,   all_products_sur,   all_customers_sur,   cashier2, count=5)
        self.stdout.write(f"   ✅ {q_hq + q_norte + q_sur} presupuestos totales")

        # Invoice series + invoices
        inv_hq    = self._seed_invoices_pro(hq, user, count=15)
        inv_norte = self._seed_invoices_pro(branch_norte, cashier1, count=8)
        inv_sur   = self._seed_invoices_pro(branch_sur,   cashier2, count=8, series_code='B')
        self.stdout.write(f"   ✅ {inv_hq + inv_norte + inv_sur} facturas emitidas")

        # Treasury
        t_info_hq    = self._seed_treasury_business(hq, user)
        t_info_norte = self._seed_treasury_pro(branch_norte, cashier1)
        self.stdout.write(f"   ✅ Treasury HQ: {t_info_hq} | Norte: {t_info_norte}")

        self.stdout.write(self.style.SUCCESS("   🎉 Plan BUSINESS completado\n"))

    # ─────────────────────────────────────────────────────────────────────────
    # SEEDERS: STOCK
    # ─────────────────────────────────────────────────────────────────────────

    def _seed_stock_start(self, business, products, user):
        """Stock for START plan: IN entries + some ADJUST movements + a few OUT."""
        count = 0
        for i, product in enumerate(products):
            # IN movement (initial stock)
            if not StockMovement.objects.filter(
                business=business, product=product, movement_type='IN'
            ).exists():
                qty = Decimal('50') + Decimal(str(i * 7 % 80))
                StockMovement.objects.create(
                    business=business, product=product,
                    movement_type='IN', quantity=qty,
                    note='Stock inicial', reason='initial_stock',
                    created_by=user,
                )
                ProductStock.objects.update_or_create(
                    business=business, product=product,
                    defaults={'quantity': qty},
                )
                count += 1

        # ADJUST movements (1 per 5 products)
        for i, product in enumerate(products):
            if i % 5 == 0:
                adj_qty = Decimal(str(5 + i % 15))
                StockMovement.objects.get_or_create(
                    business=business, product=product, movement_type='ADJUST',
                    defaults={
                        'quantity': adj_qty, 'note': 'Ajuste por inventario físico',
                        'reason': 'inventory_count', 'created_by': user,
                    }
                )
                count += 1

        # OUT movements (3 products sold manually outside system)
        for product in products[:5]:
            if not StockMovement.objects.filter(
                business=business, product=product, movement_type='OUT'
            ).exists():
                StockMovement.objects.create(
                    business=business, product=product,
                    movement_type='OUT', quantity=Decimal('5'),
                    note='Retiro para muestra', reason='sample',
                    created_by=user,
                )
                count += 1

        return count

    def _seed_stock_rich(self, business, products, user, factor=1):
        """Richer stock for PRO/BUSINESS: IN + OUT + ADJUST + WASTE."""
        count = 0
        base_date = NOW - timedelta(days=60)

        for i, product in enumerate(products):
            # Check if stock already exists
            exists = StockMovement.objects.filter(business=business, product=product).exists()
            if exists:
                continue

            # IN: initial purchase
            in_qty = Decimal(str(80 + i * 11 % 120)) * factor
            StockMovement.objects.create(
                business=business, product=product,
                movement_type='IN', quantity=in_qty,
                note='Ingreso por compra proveedor', reason='purchase',
                created_by=user,
            )
            ProductStock.objects.update_or_create(
                business=business, product=product,
                defaults={'quantity': in_qty},
            )
            count += 1

            # Second IN (replenishment)
            if i % 3 == 0:
                replenish = Decimal(str(30 + i % 40))
                StockMovement.objects.create(
                    business=business, product=product,
                    movement_type='IN', quantity=replenish,
                    note='Reposición de stock', reason='replenishment',
                    created_by=user,
                )
                ProductStock.objects.filter(business=business, product=product).update(
                    quantity=in_qty + replenish
                )
                count += 1

            # ADJUST
            if i % 4 == 0:
                adj = Decimal(str(5 + i % 20))
                StockMovement.objects.create(
                    business=business, product=product,
                    movement_type='ADJUST', quantity=adj,
                    note='Ajuste inventario físico mensual', reason='inventory_count',
                    created_by=user,
                )
                count += 1

            # OUT (manual withdrawal)
            if i % 6 == 0:
                StockMovement.objects.create(
                    business=business, product=product,
                    movement_type='OUT', quantity=Decimal('3'),
                    note='Muestras para cliente', reason='sample',
                    created_by=user,
                )
                count += 1

            # WASTE
            if i % 8 == 0:
                StockMovement.objects.create(
                    business=business, product=product,
                    movement_type='WASTE', quantity=Decimal('2'),
                    note='Producto dañado en depósito', reason='damage',
                    created_by=user,
                )
                count += 1

        return count

    # ─────────────────────────────────────────────────────────────────────────
    # SEEDERS: SALES
    # ─────────────────────────────────────────────────────────────────────────

    def _seed_sales_start(self, business, products, user):
        """25 simple sales for START plan (no cash session, varied payment methods)."""
        if Sale.objects.filter(business=business).count() >= 20:
            self.stdout.write("   ⏭️  Ventas ya existentes, saltando...")
            return Sale.objects.filter(business=business).count()

        methods = ['cash', 'transfer', 'card', 'other']
        sale_products = [
            # (product_idx, qty, discount%)
            [(0, 1, 0), (5, 2, 0)],
            [(6, 3, 0)],
            [(1, 2, 0), (2, 1, 0), (17, 1, 0)],
            [(11, 1, 5), (14, 2, 0)],
            [(3, 1, 0), (4, 1, 0)],
            [(7, 2, 10), (8, 1, 10)],
            [(19, 1, 0), (20, 2, 0)],
            [(9, 1, 0)],
            [(12, 1, 0), (13, 1, 0)],
            [(21, 2, 0), (22, 1, 0), (23, 3, 0)],
            [(0, 1, 0), (1, 1, 0)],
            [(24, 4, 0)],
            [(25, 6, 0), (26, 4, 0)],
            [(27, 1, 5)],
            [(15, 1, 0), (16, 2, 0)],
            [(10, 1, 15), (11, 1, 15)],
            [(28, 2, 0), (29, 3, 0)],
            [(18, 1, 0), (3, 2, 0)],
            [(4, 1, 0), (5, 3, 0), (24, 1, 0)],
            [(0, 2, 20)],
            [(6, 1, 0), (7, 2, 0)],
            [(19, 1, 0)],
            [(22, 2, 0), (23, 2, 0)],
            [(14, 1, 10), (15, 1, 10)],
            [(27, 1, 0), (28, 2, 0)],
        ]

        created = 0
        for idx, items_data in enumerate(sale_products):
            number = Sale.objects.filter(business=business).count() + 1
            method = methods[idx % len(methods)]
            days_ago = 45 - idx * 1
            sale_dt = NOW - timedelta(days=days_ago, hours=idx % 8 + 9)

            subtotal = Decimal('0')
            discount = Decimal('0')
            items_to_create = []
            for prod_idx, qty, disc_pct in items_data:
                if prod_idx >= len(products):
                    continue
                prod = products[prod_idx]
                unit_price = prod.price
                qty_d = Decimal(str(qty))
                line_subtotal = unit_price * qty_d
                line_discount = (line_subtotal * Decimal(str(disc_pct)) / 100).quantize(Decimal('0.01'))
                line_total = line_subtotal - line_discount
                subtotal += line_subtotal
                discount += line_discount
                items_to_create.append({
                    'product': prod,
                    'product_name_snapshot': prod.name,
                    'quantity': qty_d,
                    'unit_price': unit_price,
                    'line_total': line_total,
                })

            total = subtotal - discount
            status = 'cancelled' if idx == 7 else 'completed'
            sale = Sale.objects.create(
                business=business,
                number=number,
                status=status,
                payment_method=method,
                subtotal=subtotal,
                discount=discount,
                total=total,
                notes=f'Venta de prueba #{number}' if idx % 3 == 0 else '',
                created_by=user,
            )
            for item_data in items_to_create:
                SaleItem.objects.create(sale=sale, **item_data)
            created += 1

        return created

    def _seed_sales_pro(self, business, products, customers, user, cashier, sessions, count=35):
        """Sales with payments for PRO plan, linked to cash sessions."""
        if Sale.objects.filter(business=business).count() >= 25:
            self.stdout.write("   ⏭️  Ventas ya existentes en PRO, saltando...")
            return Sale.objects.filter(business=business).count()

        payment_combos = [
            # (method_on_sale, [(payment_method, pct_of_total)])
            ('cash',     [('cash', 100)]),
            ('transfer', [('transfer', 100)]),
            ('card',     [('credit', 100)]),
            ('card',     [('debit', 100)]),
            ('cash',     [('cash', 50), ('transfer', 50)]),
            ('card',     [('credit', 60), ('cash', 40)]),
        ]

        created = 0
        for idx in range(count):
            session = sessions[idx % len(sessions)]
            customer = customers[idx % len(customers)] if customers else None
            number = Sale.objects.filter(business=business).count() + 1
            combo = payment_combos[idx % len(payment_combos)]

            # Pick 1-3 products
            prod_set = [products[p % len(products)] for p in [idx, idx + 3, idx + 7]][:1 + idx % 3]
            subtotal = Decimal('0')
            discount = Decimal('0')
            items_to_create = []
            for pi, prod in enumerate(prod_set):
                qty = Decimal(str(1 + (idx + pi) % 4))
                unit_price = prod.price
                disc_pct = Decimal('10') if (idx + pi) % 7 == 0 else Decimal('0')
                line_sub = unit_price * qty
                line_disc = (line_sub * disc_pct / 100).quantize(Decimal('0.01'))
                line_total = line_sub - line_disc
                subtotal += line_sub
                discount += line_disc
                items_to_create.append({
                    'product': prod,
                    'product_name_snapshot': prod.name,
                    'quantity': qty,
                    'unit_price': unit_price,
                    'line_total': line_total,
                })

            total = subtotal - discount
            status = 'cancelled' if idx % 15 == 14 else 'completed'
            sale = Sale.objects.create(
                business=business,
                number=number,
                status=status,
                payment_method=combo[0],
                subtotal=subtotal,
                discount=discount,
                total=total,
                customer=customer,
                cash_session=session,
                notes=f'Cliente frecuente' if idx % 5 == 0 else '',
                created_by=cashier if idx % 2 else user,
            )
            for item_data in items_to_create:
                SaleItem.objects.create(sale=sale, **item_data)

            # Payments
            if status == 'completed':
                remaining = total
                for pidx, (pay_method, pct) in enumerate(combo[1]):
                    pay_amount = (total * Decimal(str(pct)) / 100).quantize(Decimal('0.01'))
                    if pidx == len(combo[1]) - 1:
                        pay_amount = remaining  # last payment takes the rest
                    Payment.objects.create(
                        business=business,
                        sale=sale,
                        session=session,
                        method=pay_method,
                        amount=pay_amount,
                        created_by=cashier,
                    )
                    remaining -= pay_amount

            created += 1

        return created

    def _seed_sales_business(self, business, products, customers, user, cashier, sessions, count=30):
        """Sales for BUSINESS plan."""
        if Sale.objects.filter(business=business).count() >= count - 5:
            return Sale.objects.filter(business=business).count()

        return self._seed_sales_pro(business, products, customers, user, cashier, sessions, count=count)

    # ─────────────────────────────────────────────────────────────────────────
    # SEEDERS: CASH
    # ─────────────────────────────────────────────────────────────────────────

    def _create_cash_registers_pro(self, business):
        reg1, _ = CashRegister.objects.get_or_create(
            business=business, name='Caja N°1 - Principal',
            defaults={'is_active': True}
        )
        reg2, _ = CashRegister.objects.get_or_create(
            business=business, name='Caja N°2 - Secundaria',
            defaults={'is_active': True}
        )
        return reg1, reg2

    def _get_or_create_cash_register(self, business, name):
        reg, _ = CashRegister.objects.get_or_create(
            business=business, name=name,
            defaults={'is_active': True}
        )
        return reg

    def _create_cash_session(
        self, business, register, opened_by,
        daysago_open=0, daysago_close=None, close_hour=21,
        opening_amount=Decimal('5000'), closing_counted=None,
    ):
        """Creates a cash session. If daysago_close is set, the session is closed."""
        opened_at = NOW - timedelta(days=daysago_open, hours=0) if daysago_open > 0 else NOW - timedelta(hours=2)
        opened_at = opened_at.replace(hour=8, minute=0, second=0, microsecond=0)

        # Check for existing open session on this register
        existing_open = CashSession.objects.filter(register=register, status='open').first()
        if existing_open:
            if daysago_close is None:
                # Wanted open session but one already exists — return existing
                return existing_open
            # Close the existing open session first (to avoid constraint violation)
            # Just return it for already-seeded scenario
            return existing_open

        is_closed = daysago_close is not None
        if is_closed:
            closed_at = NOW - timedelta(days=daysago_close)
            closed_at = closed_at.replace(hour=close_hour, minute=30, second=0, microsecond=0)
        else:
            closed_at = None

        session = CashSession.objects.create(
            business=business,
            register=register,
            opened_by=opened_by,
            opened_by_name=opened_by.get_full_name() or opened_by.username,
            opening_cash_amount=opening_amount,
            status='closed' if is_closed else 'open',
            closed_by=opened_by if is_closed else None,
            closing_cash_counted=closing_counted if is_closed else None,
            expected_cash_total=closing_counted if is_closed else None,
            difference_amount=Decimal('0') if is_closed else None,
            closing_note='Cierre de jornada' if is_closed else '',
            opened_at=opened_at,
            closed_at=closed_at,
        )
        return session

    def _seed_cash_movements(self, business, sessions, user, count=4):
        """Creates extra cash movements (deposits, expense withdrawals) in sessions."""
        templates = [
            ('in', 'deposit', 'cash', '5000', 'Depósito efectivo inicio turno'),
            ('out', 'expense', 'cash', '2500', 'Pago proveedor delivery'),
            ('out', 'withdraw', 'cash', '1500', 'Retiro para gastos menores'),
            ('in', 'deposit', 'transfer', '8000', 'Transferencia recibida'),
            ('out', 'expense', 'cash', '3000', 'Pago servicio de limpieza'),
            ('in', 'other', 'cash', '1000', 'Fondo de cambio añadido'),
        ]
        created = 0
        for i, session in enumerate(sessions):
            for j in range(min(count, len(templates))):
                t = templates[(i * count + j) % len(templates)]
                exists = CashMovement.objects.filter(
                    business=business, session=session,
                    movement_type=t[0], note=t[4],
                ).exists()
                if not exists:
                    CashMovement.objects.create(
                        business=business,
                        session=session,
                        movement_type=t[0],
                        category=t[1],
                        method=t[2],
                        amount=Decimal(t[3]),
                        note=t[4],
                        created_by=user,
                    )
                    created += 1
        return created

    # ─────────────────────────────────────────────────────────────────────────
    # SEEDERS: CUSTOMERS
    # ─────────────────────────────────────────────────────────────────────────

    def _create_customers(self, business, customer_data_list):
        customers = []
        for c in customer_data_list:
            existing = Customer.objects.filter(
                business=business,
                name=c['name'],
            ).first()
            if existing:
                customers.append(existing)
                continue
            
            # Check doc uniqueness
            doc_type = c.get('doc_type', '')
            doc_number = c.get('doc_number', '')
            if doc_type and doc_number:
                existing_doc = Customer.objects.filter(
                    business=business, doc_type=doc_type, doc_number=doc_number
                ).first()
                if existing_doc:
                    customers.append(existing_doc)
                    continue

            customer = Customer.objects.create(
                business=business,
                name=c['name'],
                type=c.get('type', 'individual'),
                doc_type=c.get('doc_type', ''),
                doc_number=c.get('doc_number', ''),
                tax_condition=c.get('tax_condition', 'consumer'),
                email=c.get('email', ''),
                phone=c.get('phone', ''),
                address_line=c.get('address', ''),
                city=c.get('city', ''),
                province=c.get('province', 'Buenos Aires'),
                country='Argentina',
                is_active=True,
            )
            customers.append(customer)
        return customers

    # ─────────────────────────────────────────────────────────────────────────
    # SEEDERS: QUOTES
    # ─────────────────────────────────────────────────────────────────────────

    def _seed_quotes(self, business, products, customers, user, count=10):
        if Quote.objects.filter(business=business).count() >= count - 2:
            return Quote.objects.filter(business=business).count()

        seq, _ = QuoteSequence.objects.get_or_create(business=business)

        statuses = ['draft', 'sent', 'accepted', 'rejected', 'expired', 'converted', 'draft', 'sent', 'accepted', 'rejected', 'draft', 'sent']
        notes_map = {
            'draft': 'Pendiente de revisión interna',
            'sent': 'Enviado al cliente por email',
            'accepted': 'Cliente confirmó la propuesta',
            'rejected': 'Cliente rechazó por precio',
            'expired': 'Venció sin respuesta del cliente',
            'converted': 'Convertido a venta',
        }

        created = 0
        for i in range(count):
            status = statuses[i % len(statuses)]
            seq.last_number += 1
            seq.save(update_fields=['last_number'])
            number = f"P-{str(seq.last_number).zfill(6)}"

            # Avoid duplicate number
            if Quote.objects.filter(business=business, number=number).exists():
                continue

            days_ago = count - i + 2
            customer = customers[i % len(customers)] if customers else None
            valid_until = TODAY + timedelta(days=30) if status in ['draft', 'sent'] else TODAY - timedelta(days=i * 2)

            # Items: 2-3 products
            prod_set = [products[p % len(products)] for p in [i, i + 2, i + 5]][:2 + i % 2]
            subtotal = Decimal('0')
            items_to_create = []
            for pi, prod in enumerate(prod_set):
                qty = Decimal(str(1 + pi))
                unit_price = prod.price
                disc = (unit_price * Decimal('5') / 100).quantize(Decimal('0.01')) if i % 4 == 0 else Decimal('0')
                line_total = (unit_price * qty) - (disc * qty)
                subtotal += line_total
                items_to_create.append({
                    'product': prod,
                    'name_snapshot': prod.name,
                    'quantity': qty,
                    'unit_price': unit_price,
                    'discount': disc,
                    'total_line': line_total,
                })

            quote = Quote.objects.create(
                business=business,
                number=number,
                status=status,
                customer=customer if customer else None,
                customer_name=customer.name if customer else f'Cliente Ocas. {i+1}',
                customer_email=customer.email if customer else '',
                valid_until=valid_until,
                notes=notes_map.get(status, ''),
                terms='Precios en pesos argentinos. IVA incluido.',
                currency='ARS',
                subtotal=subtotal,
                discount_total=Decimal('0'),
                tax_total=Decimal('0'),
                total=subtotal,
                created_by=user,
            )
            for item_data in items_to_create:
                QuoteItem.objects.create(quote=quote, **item_data)
            created += 1

        return created

    # ─────────────────────────────────────────────────────────────────────────
    # SEEDERS: INVOICES
    # ─────────────────────────────────────────────────────────────────────────

    def _seed_invoices_pro(self, business, user, count=10, series_code='B'):
        """Creates invoice series and invoices linked to completed sales."""
        series, _ = InvoiceSeries.objects.get_or_create(
            business=business, code=series_code,
            defaults={'prefix': '0001', 'next_number': 1, 'is_active': True},
        )

        # Also create a DocumentSeries counterpart
        DocumentSeries.objects.get_or_create(
            business=business,
            document_type='invoice',
            letter=series_code,
            point_of_sale='0001',
            defaults={
                'prefix': '',
                'suffix': '',
                'next_number': 1,
                'is_active': True,
                'is_default': True,
            }
        )

        # Get completed sales without invoices
        uninvoiced_sales = Sale.objects.filter(
            business=business, status='completed'
        ).exclude(
            invoice__isnull=False
        ).order_by('number')[:count]

        created = 0
        for sale in uninvoiced_sales:
            number = series.next_number
            full_number = series.format_full_number(number)

            if Invoice.objects.filter(business=business, series=series, number=number).exists():
                series.next_number += 1
                series.save(update_fields=['next_number'])
                continue

            customer = sale.customer
            Invoice.objects.create(
                business=business,
                sale=sale,
                series=series,
                number=number,
                full_number=full_number,
                status='issued',
                issued_at=sale.created_at,
                customer_name=customer.name if customer else 'Consumidor Final',
                customer_tax_id=customer.doc_number if customer else '',
                customer_address=customer.address_line if customer else '',
                subtotal=sale.subtotal,
                discount=sale.discount,
                total=sale.total,
                created_by=user,
            )
            series.next_number += 1
            series.save(update_fields=['next_number'])
            created += 1

        return created

    # ─────────────────────────────────────────────────────────────────────────
    # SEEDERS: TREASURY PRO
    # ─────────────────────────────────────────────────────────────────────────

    def _seed_treasury_pro(self, business, user):
        if TreasuryAccount.objects.filter(business=business).count() >= 3:
            return "ya existente, saltando"

        # Accounts
        acc_cash, _ = TreasuryAccount.objects.get_or_create(
            business=business, name='Caja Principal',
            defaults={'type': 'cash', 'currency': 'ARS', 'opening_balance': Decimal('5000'), 'opening_balance_date': TODAY - timedelta(days=90)},
        )
        acc_bank, _ = TreasuryAccount.objects.get_or_create(
            business=business, name='Cuenta Banco Nación',
            defaults={'type': 'bank', 'currency': 'ARS', 'opening_balance': Decimal('50000'), 'opening_balance_date': TODAY - timedelta(days=90)},
        )
        acc_mp, _ = TreasuryAccount.objects.get_or_create(
            business=business, name='MercadoPago',
            defaults={'type': 'mercadopago', 'currency': 'ARS', 'opening_balance': Decimal('0'), 'opening_balance_date': TODAY - timedelta(days=90)},
        )

        # TreasurySettings
        ts, _ = TreasurySettings.objects.get_or_create(business=business)
        ts.default_cash_account = acc_cash
        ts.default_bank_account = acc_bank
        ts.default_mercadopago_account = acc_mp
        ts.save()

        # Categories
        cat_ventas, _ = TreasuryCategory.objects.get_or_create(business=business, name='Ventas', direction='income')
        cat_servicios_ingreso, _ = TreasuryCategory.objects.get_or_create(business=business, name='Servicios prestados', direction='income')
        cat_devolucion, _ = TreasuryCategory.objects.get_or_create(business=business, name='Devolución de gastos', direction='income')
        cat_alquiler, _ = TreasuryCategory.objects.get_or_create(business=business, name='Alquiler', direction='expense')
        cat_serv_pub, _ = TreasuryCategory.objects.get_or_create(business=business, name='Servicios públicos', direction='expense')
        cat_proveed, _ = TreasuryCategory.objects.get_or_create(business=business, name='Proveedores', direction='expense')

        # Transactions (25 across 3 months)
        transactions_data = [
            # (account, direction, amount, category, description, days_ago)
            (acc_cash,  'IN',  '25000', cat_ventas,          'Ingresos ventas semana 1', 85),
            (acc_bank,  'IN',  '38000', cat_ventas,          'Transferencia ventas mes anterior', 82),
            (acc_cash,  'OUT', '12000', cat_alquiler,        'Pago alquiler local octubre', 80),
            (acc_cash,  'OUT', '2800',  cat_serv_pub,        'Pago factura luz octubre', 78),
            (acc_cash,  'OUT', '1500',  cat_serv_pub,        'Pago internet octubre', 77),
            (acc_bank,  'OUT', '45000', cat_proveed,         'Compra mercadería proveedor A', 75),
            (acc_mp,    'IN',  '18000', cat_ventas,          'Cobros MercadoPago sem 1 oct', 70),
            (acc_cash,  'IN',  '31000', cat_ventas,          'Ingresos ventas semana 2', 67),
            (acc_bank,  'IN',  '15000', cat_servicios_ingreso,'Servicio asesoramiento oct', 65),
            (acc_cash,  'OUT', '12000', cat_alquiler,        'Pago alquiler local noviembre', 50),
            (acc_cash,  'OUT', '3100',  cat_serv_pub,        'Pago factura luz noviembre', 48),
            (acc_cash,  'OUT', '1500',  cat_serv_pub,        'Pago internet noviembre', 47),
            (acc_bank,  'OUT', '62000', cat_proveed,         'Compra mercadería proveedor B', 45),
            (acc_mp,    'IN',  '24000', cat_ventas,          'Cobros MercadoPago oct completo', 42),
            (acc_cash,  'IN',  '28000', cat_ventas,          'Ingresos ventas sem 1 nov', 38),
            (acc_bank,  'IN',  '42000', cat_ventas,          'Transferencia ventas noviembre', 35),
            (acc_bank,  'OUT', '55000', cat_proveed,         'Pago proveedor importación', 32),
            (acc_cash,  'OUT', '12000', cat_alquiler,        'Pago alquiler local diciembre', 20),
            (acc_cash,  'OUT', '2950',  cat_serv_pub,        'Pago factura luz diciembre', 18),
            (acc_cash,  'OUT', '1500',  cat_serv_pub,        'Pago internet diciembre', 17),
            (acc_mp,    'IN',  '31500', cat_ventas,          'Cobros MercadoPago nov completo', 15),
            (acc_cash,  'IN',  '35000', cat_ventas,          'Ingresos ventas sem 1 dic', 12),
            (acc_bank,  'IN',  '50000', cat_ventas,          'Transferencia ventas dic', 10),
            (acc_bank,  'OUT', '38000', cat_proveed,         'Pago proveedor mensual dic', 8),
            (acc_cash,  'IN',  '1500',  cat_devolucion,      'Reembolso por devolución proveedor', 5),
        ]

        tx_count = 0
        for acc, direction, amount, cat, desc, days_ago in transactions_data:
            occurred_at = NOW - timedelta(days=days_ago)
            if not TreasuryTransaction.objects.filter(business=business, description=desc).exists():
                TreasuryTransaction.objects.create(
                    business=business,
                    account=acc,
                    direction=direction,
                    amount=Decimal(amount),
                    occurred_at=occurred_at,
                    category=cat,
                    description=desc,
                    status='posted',
                    created_by=user,
                )
                tx_count += 1

        # Fixed expenses (3 expenses × 3 months = 9 periods)
        fixed_expenses_data = [
            ('Alquiler Local', Decimal('12000'), 1),
            ('Servicio de Luz', None, 5),
            ('Internet y Telefonía', Decimal('1500'), 10),
        ]
        for name, amount, due_day in fixed_expenses_data:
            fe, _ = FixedExpense.objects.get_or_create(
                business=business, name=name,
                defaults={'default_amount': amount, 'due_day': due_day, 'frequency': 'monthly', 'is_active': True},
            )
            for m in range(3):
                period_date = (TODAY.replace(day=1) - timedelta(days=30 * m)).replace(day=1)
                period_amount = amount or Decimal('2800') + Decimal(str(m * 150))
                status = 'paid' if m > 0 else 'pending'
                paid_at = NOW - timedelta(days=30 * m + 5) if status == 'paid' else None
                period, _ = FixedExpensePeriod.objects.get_or_create(
                    fixed_expense=fe, period=period_date,
                    defaults={
                        'amount': period_amount,
                        'status': status,
                        'paid_at': paid_at,
                        'paid_account': acc_cash if status == 'paid' else None,
                    }
                )

        # Expenses (standalone)
        expenses_data = [
            ('Gastos de papelería', cat_serv_pub, '850', 30, 'paid'),
            ('Mantenimiento PC', cat_proveed, '5000', 25, 'paid'),
            ('Capacitación personal', cat_servicios_ingreso, '8000', 15, 'pending'),
            ('Publicidad redes sociales', cat_serv_pub, '3500', 10, 'pending'),
            ('Seguro del local', cat_alquiler, '6000', 5, 'paid'),
        ]
        for name, cat, amount, days_ago, status in expenses_data:
            due_date = TODAY - timedelta(days=days_ago) if status == 'paid' else TODAY + timedelta(days=5)
            paid_at = NOW - timedelta(days=days_ago) if status == 'paid' else None
            if not Expense.objects.filter(business=business, name=name).exists():
                Expense.objects.create(
                    business=business,
                    name=name,
                    category=cat,
                    amount=Decimal(amount),
                    due_date=due_date,
                    status=status,
                    paid_at=paid_at,
                    paid_account=acc_cash if status == 'paid' else None,
                )

        return f"3 cuentas, 6 categorías, {tx_count} transacciones, 3 gastos fijos, 5 gastos standalone"

    # ─────────────────────────────────────────────────────────────────────────
    # SEEDERS: TREASURY BUSINESS (extended)
    # ─────────────────────────────────────────────────────────────────────────

    def _seed_treasury_business(self, business, user):
        if TreasuryAccount.objects.filter(business=business).count() >= 5:
            return "ya existente, saltando"

        # Accounts (5)
        acc_cash, _ = TreasuryAccount.objects.get_or_create(
            business=business, name='Caja HQ Central',
            defaults={'type': 'cash', 'currency': 'ARS', 'opening_balance': Decimal('10000'), 'opening_balance_date': TODAY - timedelta(days=120)},
        )
        acc_bank1, _ = TreasuryAccount.objects.get_or_create(
            business=business, name='Banco Galicia Cta Cte',
            defaults={'type': 'bank', 'currency': 'ARS', 'opening_balance': Decimal('150000'), 'opening_balance_date': TODAY - timedelta(days=120)},
        )
        acc_bank2, _ = TreasuryAccount.objects.get_or_create(
            business=business, name='Banco Santander Cta Cte',
            defaults={'type': 'bank', 'currency': 'ARS', 'opening_balance': Decimal('80000'), 'opening_balance_date': TODAY - timedelta(days=90)},
        )
        acc_mp, _ = TreasuryAccount.objects.get_or_create(
            business=business, name='MercadoPago Empresas',
            defaults={'type': 'mercadopago', 'currency': 'ARS', 'opening_balance': Decimal('25000'), 'opening_balance_date': TODAY - timedelta(days=90)},
        )
        acc_card, _ = TreasuryAccount.objects.get_or_create(
            business=business, name='Flotante Tarjetas',
            defaults={'type': 'card_float', 'currency': 'ARS', 'opening_balance': Decimal('0'), 'opening_balance_date': TODAY - timedelta(days=60)},
        )

        ts, _ = TreasurySettings.objects.get_or_create(business=business)
        ts.default_cash_account = acc_cash
        ts.default_bank_account = acc_bank1
        ts.default_mercadopago_account = acc_mp
        ts.save()

        # Categories (8)
        cat_ventas, _ = TreasuryCategory.objects.get_or_create(business=business, name='Ventas y Facturación', direction='income')
        cat_financ, _ = TreasuryCategory.objects.get_or_create(business=business, name='Financiero', direction='income')
        cat_otros_ing, _ = TreasuryCategory.objects.get_or_create(business=business, name='Otros Ingresos', direction='income')
        cat_devol, _ = TreasuryCategory.objects.get_or_create(business=business, name='Devoluciones Recibidas', direction='income')
        cat_alquiler, _ = TreasuryCategory.objects.get_or_create(business=business, name='Alquiler', direction='expense')
        cat_salarios, _ = TreasuryCategory.objects.get_or_create(business=business, name='Salarios y Cargas Sociales', direction='expense')
        cat_proveed, _ = TreasuryCategory.objects.get_or_create(business=business, name='Proveedores', direction='expense')
        cat_serv, _ = TreasuryCategory.objects.get_or_create(business=business, name='Servicios y Gastos Fijos', direction='expense')
        cat_impuestos, _ = TreasuryCategory.objects.get_or_create(business=business, name='Impuestos y Tasas', direction='expense')

        # 50 transactions across 4 months
        txn_templates = [
            (acc_bank1, 'IN',  '125000', cat_ventas,   'Cobranzas venta mayorista mes 1', 110),
            (acc_cash,  'IN',  '48000',  cat_ventas,   'Ventas contado semana 1', 108),
            (acc_bank1, 'OUT', '35000',  cat_alquiler, 'Alquiler sede central mes 1', 105),
            (acc_bank2, 'OUT', '28000',  cat_alquiler, 'Alquiler sucursal Norte mes 1', 104),
            (acc_bank1, 'OUT', '22000',  cat_alquiler, 'Alquiler sucursal Sur mes 1', 103),
            (acc_bank1, 'OUT', '185000', cat_proveed,  'Compra mercadería importada lote 1', 100),
            (acc_mp,    'IN',  '52000',  cat_ventas,   'Cobros MP sem 1-2', 98),
            (acc_card,  'IN',  '67000',  cat_ventas,   'Liquidación tarjetas semana 1', 95),
            (acc_bank1, 'OUT', '120000', cat_salarios, 'Sueldos personal mes 1', 92),
            (acc_bank1, 'OUT', '38000',  cat_serv,     'Servicios y servicios básicos mes 1', 90),
            (acc_cash,  'IN',  '55000',  cat_ventas,   'Ventas contado quinc. 2 mes 1', 88),
            (acc_bank1, 'IN',  '98000',  cat_ventas,   'Cobranzas cuentas corrientes', 85),
            (acc_bank1, 'OUT', '15000',  cat_impuestos,'IVA mensual mes 1', 82),
            (acc_bank1, 'OUT', '8500',   cat_impuestos,'Ingresos brutos mes 1', 80),
            (acc_bank2, 'OUT', '150000', cat_proveed,  'Proveedor local mercadería mes 1', 78),
            (acc_bank1, 'IN',  '135000', cat_ventas,   'Cobranzas venta mayorista mes 2', 75),
            (acc_cash,  'IN',  '62000',  cat_ventas,   'Ventas contado sem 1 mes 2', 73),
            (acc_bank1, 'OUT', '35000',  cat_alquiler, 'Alquiler sede central mes 2', 70),
            (acc_bank2, 'OUT', '28000',  cat_alquiler, 'Alquiler sucursal Norte mes 2', 69),
            (acc_bank1, 'OUT', '22000',  cat_alquiler, 'Alquiler sucursal Sur mes 2', 68),
            (acc_mp,    'IN',  '71000',  cat_ventas,   'Cobros MP mes 2', 65),
            (acc_card,  'IN',  '89000',  cat_ventas,   'Liquidación tarjetas mes 2', 62),
            (acc_bank1, 'OUT', '125000', cat_salarios, 'Sueldos personal mes 2', 60),
            (acc_bank1, 'OUT', '41000',  cat_serv,     'Servicios y gastos fijos mes 2', 58),
            (acc_bank1, 'OUT', '220000', cat_proveed,  'Compra mercadería proveedor externo m2', 55),
            (acc_bank1, 'IN',  '18000',  cat_financ,   'Rendimiento plazo fijo 30 días', 52),
            (acc_bank1, 'IN',  '112000', cat_ventas,   'Cobranzas mes 3', 45),
            (acc_cash,  'IN',  '75000',  cat_ventas,   'Ventas contado mes 3 sem 1-2', 43),
            (acc_bank1, 'OUT', '35000',  cat_alquiler, 'Alquiler sede central mes 3', 40),
            (acc_bank2, 'OUT', '28000',  cat_alquiler, 'Alquiler sucursal Norte mes 3', 39),
            (acc_bank1, 'OUT', '22000',  cat_alquiler, 'Alquiler sucursal Sur mes 3', 38),
            (acc_bank1, 'OUT', '132000', cat_salarios, 'Sueldos personal mes 3 + SAC', 35),
            (acc_bank1, 'OUT', '39000',  cat_serv,     'Servicios y gastos fijos mes 3', 33),
            (acc_mp,    'IN',  '85000',  cat_ventas,   'Cobros MP mes 3', 30),
            (acc_card,  'IN',  '95000',  cat_ventas,   'Liquidación tarjetas mes 3', 28),
            (acc_bank1, 'OUT', '18000',  cat_impuestos,'IVA mensual mes 3', 25),
            (acc_bank1, 'OUT', '9200',   cat_impuestos,'Ingresos brutos mes 3', 23),
            (acc_bank2, 'OUT', '175000', cat_proveed,  'Pago proveedor mes 3', 20),
            (acc_bank1, 'IN',  '145000', cat_ventas,   'Cobranzas mes 4 quinc 1', 18),
            (acc_cash,  'IN',  '82000',  cat_ventas,   'Ventas contado mes 4 sem 1', 15),
            (acc_mp,    'IN',  '95000',  cat_ventas,   'Cobros MP quinc 1 mes 4', 12),
            (acc_card,  'IN',  '110000', cat_ventas,   'Liquidación tarjetas mes 4', 10),
            (acc_bank1, 'OUT', '35000',  cat_alquiler, 'Alquiler sede central mes 4', 8),
            (acc_bank1, 'OUT', '135000', cat_salarios, 'Sueldos personal mes 4', 6),
            (acc_bank1, 'OUT', '195000', cat_proveed,  'Compra mercadería mes 4', 5),
            (acc_bank1, 'OUT', '42000',  cat_serv,     'Servicios y gastos fijos mes 4', 4),
            (acc_bank1, 'IN',  '5000',   cat_devol,    'Devolución proveedor por productos dañados', 3),
            (acc_bank1, 'OUT', '21000',  cat_impuestos,'IVA mensual mes 4', 2),
            (acc_bank1, 'IN',  '22000',  cat_financ,   'Rendimiento plazo fijo mes 4', 1),
            (acc_cash,  'IN',  '18000',  cat_otros_ing,'Ingreso especial por evento', 0),
        ]

        tx_count = 0
        for acc, direction, amount, cat, desc, days_ago in txn_templates:
            occurred_at = NOW - timedelta(days=days_ago, hours=10)
            if not TreasuryTransaction.objects.filter(business=business, description=desc).exists():
                TreasuryTransaction.objects.create(
                    business=business, account=acc, direction=direction,
                    amount=Decimal(amount), occurred_at=occurred_at,
                    category=cat, description=desc, status='posted', created_by=user,
                )
                tx_count += 1

        # Fixed expenses (5 × 3 months = 15 periods)
        fe_data = [
            ('Alquiler Sede Central', Decimal('35000'), 1),
            ('Alquiler Sucursal Norte', Decimal('28000'), 1),
            ('Alquiler Sucursal Sur', Decimal('22000'), 1),
            ('Servicios Básicos HQ', None, 10),
            ('Internet y Telefonía Empresarial', Decimal('8500'), 15),
        ]
        for name, amount, due_day in fe_data:
            fe, _ = FixedExpense.objects.get_or_create(
                business=business, name=name,
                defaults={'default_amount': amount, 'due_day': due_day, 'frequency': 'monthly', 'is_active': True},
            )
            for m in range(3):
                period_date = (TODAY.replace(day=1) - timedelta(days=30 * m)).replace(day=1)
                period_amount = amount or Decimal('12000') + Decimal(str(m * 500))
                status = 'paid' if m > 0 else 'pending'
                paid_at = NOW - timedelta(days=30 * m + 3) if status == 'paid' else None
                FixedExpensePeriod.objects.get_or_create(
                    fixed_expense=fe, period=period_date,
                    defaults={
                        'amount': period_amount, 'status': status,
                        'paid_at': paid_at,
                        'paid_account': acc_bank1 if status == 'paid' else None,
                    }
                )

        # Employees (5) + payroll
        emp_data = [
            ('Lucía Manzano', '27-12345678-9', 'monthly', Decimal('180000')),
            ('Rodrigo Ibáñez', '27-98765432-1', 'monthly', Decimal('165000')),
            ('Carla Suárez', '27-11223344-5', 'monthly', Decimal('155000')),
            ('Tomás Benitez', '27-44556677-8', 'monthly', Decimal('145000')),
            ('Valeria Quiroga', '27-87654321-0', 'monthly', Decimal('140000')),
        ]
        for full_name, identifier, freq, salary in emp_data:
            emp, _ = Employee.objects.get_or_create(
                business=business, full_name=full_name,
                defaults={'identifier': identifier, 'pay_frequency': freq, 'base_salary': salary, 'is_active': True},
            )
            # 2 payroll payments per employee (last 2 months)
            for m in range(2):
                paid_at = NOW - timedelta(days=30 * m + 25)
                if not PayrollPayment.objects.filter(business=business, employee=emp).filter(
                    paid_at__year=paid_at.year, paid_at__month=paid_at.month
                ).exists():
                    tx = TreasuryTransaction.objects.create(
                        business=business, account=acc_bank1,
                        direction='OUT', amount=salary,
                        occurred_at=paid_at,
                        category=cat_salarios,
                        description=f'Sueldo {full_name} - {paid_at.strftime("%B %Y")}',
                        status='posted', created_by=user,
                    )
                    PayrollPayment.objects.create(
                        business=business, employee=emp,
                        amount=salary, paid_at=paid_at,
                        account=acc_bank1, transaction=tx,
                    )

        return f"5 cuentas, 9 categorías, {tx_count} transacciones, 5 gastos fijos, 5 empleados con nómina"

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _get_business(self, name):
        return Business.objects.filter(name=name, parent=None).first()

    def _get_or_create_branch(self, hq, name, user, suffix):
        branch, created = Business.objects.get_or_create(
            name=name, parent=hq,
            defaults={'default_service': 'gestion', 'status': 'active'},
        )
        if created:
            # CommercialSettings auto-created by signal; ensure it's configured
            cs, _ = CommercialSettings.objects.get_or_create(business=branch)
            cs.allow_sell_without_stock = False
            cs.block_sales_if_no_open_cash_session = False
            cs.save()
        return branch

    def _setup_billing_profile(self, business, legal_name, tax_id, vat_condition, address='', email='', phone=''):
        profile, _ = BusinessBillingProfile.objects.get_or_create(business=business)
        profile.legal_name = legal_name
        profile.tax_id = tax_id
        profile.tax_id_type = 'cuit'
        profile.vat_condition = vat_condition
        profile.commercial_address = address
        profile.fiscal_address = address
        profile.email = email
        profile.phone = phone
        profile.trade_name = legal_name
        profile.save()

    def _get_or_create_user(self, email, username, password='Demo12345!'):
        user, created = User.objects.get_or_create(
            email=email,
            defaults={'username': username, 'is_active': True, 'is_staff': False},
        )
        if created:
            user.set_password(password)
            user.save()
        return user

    def _get_or_create_membership(self, user, business, role):
        membership, _ = Membership.objects.get_or_create(
            user=user, business=business,
            defaults={'role': role},
        )
        return membership

    def _create_categories(self, business, names):
        categories = []
        for name in names:
            cat, _ = ProductCategory.objects.get_or_create(
                business=business, name=name,
                defaults={'is_active': True},
            )
            categories.append(cat)
        return categories

    def _create_products_from_list(self, business, categories, product_list, user):
        products = []
        for name, sku, cat_idx, cost, price, stock_min in product_list:
            cat = categories[cat_idx % len(categories)]
            product, created = Product.objects.get_or_create(
                business=business, sku=sku,
                defaults={
                    'name': name,
                    'category': cat,
                    'cost': Decimal(str(cost)),
                    'price': Decimal(str(price)),
                    'stock_min': Decimal(str(stock_min // 10)),
                    'is_active': True,
                }
            )
            if not created:
                # Update price/cost if stale
                product.price = Decimal(str(price))
                product.cost = Decimal(str(cost))
                product.save(update_fields=['price', 'cost'])
            products.append(product)
        return products
