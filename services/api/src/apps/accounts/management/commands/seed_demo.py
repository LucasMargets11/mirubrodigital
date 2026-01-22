from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, Subscription
from apps.cash.models import CashMovement, CashRegister, CashSession, Payment
from apps.cash.services import compute_session_totals
from apps.catalog.models import Product
from apps.customers.models import Customer
from apps.inventory.models import ProductStock, StockMovement
from apps.inventory.services import ensure_stock_record, register_stock_movement
from apps.invoices.models import Invoice, InvoiceSeries
from apps.sales.models import Sale
from apps.sales.serializers import SaleCancelSerializer, SaleCreateSerializer

LOGIN_URL = 'http://localhost:3000/entrar'
ACTIVE_STATUS = 'active'
DEFAULT_PASSWORD = 'mirubro123'

DEMO_BUSINESSES: List[Dict[str, object]] = [
  {
    'name': 'Manzana',
    'default_service': 'gestion',
    'service_label': 'Gestión Comercial',
    'plan': BusinessPlan.PRO,
    'customers': [
      {
        'code': 'carolina-costa',
        'name': 'Carolina Costa',
        'type': 'individual',
        'doc_type': 'dni',
        'doc_number': '30123456',
        'tax_condition': 'consumer',
        'email': 'carolina.costa@demo.local',
        'phone': '+54 9 11 5555-1010',
        'address_line': 'Av. Siempre Viva 123',
        'city': 'Buenos Aires',
        'province': 'Buenos Aires',
        'postal_code': '1001',
        'country': 'Argentina',
        'note': 'Visita el local todos los lunes a la mañana.',
      },
      {
        'code': 'emilia-suarez',
        'name': 'Emilia Suárez',
        'type': 'individual',
        'doc_type': 'dni',
        'doc_number': '28456789',
        'tax_condition': 'consumer',
        'email': 'emilia.suarez@demo.local',
        'phone': '+54 9 11 5555-5454',
        'address_line': 'Lavalle 980',
        'city': 'Buenos Aires',
        'province': 'Buenos Aires',
        'postal_code': '1047',
        'country': 'Argentina',
      },
      {
        'code': 'julian-peretti',
        'name': 'Julián Peretti',
        'type': 'individual',
        'doc_type': 'dni',
        'doc_number': '27567890',
        'tax_condition': 'consumer',
        'email': 'julian.peretti@demo.local',
        'phone': '+54 9 11 5555-2121',
        'address_line': 'Chile 2350',
        'city': 'Buenos Aires',
        'province': 'Buenos Aires',
        'postal_code': '1260',
        'country': 'Argentina',
        'note': 'Prefiere pagar con tarjeta y factura A.',
      },
      {
        'code': 'lucia-y-sons',
        'name': 'Lucía y Sons SRL',
        'type': 'company',
        'doc_type': 'cuit',
        'doc_number': '30-71458963-7',
        'tax_condition': 'registered',
        'email': 'compras@luciasons.com',
        'phone': '+54 9 11 5555-8888',
        'address_line': 'Brandsen 2001',
        'city': 'Avellaneda',
        'province': 'Buenos Aires',
        'postal_code': '1870',
        'country': 'Argentina',
        'note': 'Compra catering para oficinas una vez por semana.',
      },
      {
        'code': 'eco-estudio',
        'name': 'Eco Estudio Creativo',
        'type': 'company',
        'doc_type': 'cuit',
        'doc_number': '30-61547852-3',
        'tax_condition': 'monotax',
        'email': 'hola@ecoestudio.com',
        'phone': '+54 9 11 5555-6060',
        'address_line': 'Gorriti 4210',
        'city': 'Buenos Aires',
        'province': 'Buenos Aires',
        'postal_code': '1185',
        'country': 'Argentina',
      },
      {
        'code': 'club-runner',
        'name': 'Club Runner Palermo',
        'type': 'company',
        'doc_type': 'cuit',
        'doc_number': '30-63322158-9',
        'tax_condition': 'registered',
        'email': 'contacto@clubrunner.com',
        'phone': '+54 9 11 5555-9090',
        'address_line': 'Olleros 2225',
        'city': 'Buenos Aires',
        'province': 'Buenos Aires',
        'postal_code': '1426',
        'country': 'Argentina',
      },
    ],
    'users': [
      {'email': 'manzana.owner@mirubro.local', 'name': 'Manzana Owner', 'role': 'owner'},
      {'email': 'manzana.manager@mirubro.local', 'name': 'Manzana Manager', 'role': 'manager'},
      {'email': 'manzana.cashier@mirubro.local', 'name': 'Manzana Caja', 'role': 'cashier'},
      {'email': 'manzana.staff@mirubro.local', 'name': 'Manzana Staff', 'role': 'staff'},
      {'email': 'manzana.viewer@mirubro.local', 'name': 'Manzana Viewer', 'role': 'viewer'},
    ],
  },
  {
    'name': 'La Pizza',
    'default_service': 'restaurante',
    'service_label': 'Restaurantes',
    'plan': BusinessPlan.PLUS,
    'customers': [
      {
        'code': 'agustin-ferraro',
        'name': 'Agustín Ferraro',
        'type': 'individual',
        'doc_type': 'dni',
        'doc_number': '29567441',
        'tax_condition': 'consumer',
        'email': 'agustin.ferraro@demo.local',
        'phone': '+54 9 11 5555-3030',
        'address_line': 'Arribeños 3500',
        'city': 'Buenos Aires',
        'province': 'Buenos Aires',
        'postal_code': '1429',
        'country': 'Argentina',
      },
      {
        'code': 'martina-cabrera',
        'name': 'Martina Cabrera',
        'type': 'individual',
        'doc_type': 'dni',
        'doc_number': '27987411',
        'tax_condition': 'consumer',
        'email': 'martina.cabrera@demo.local',
        'phone': '+54 9 11 5555-0202',
        'address_line': 'Dorrego 1635',
        'city': 'Buenos Aires',
        'province': 'Buenos Aires',
        'postal_code': '1414',
        'country': 'Argentina',
      },
      {
        'code': 'estudio-tafi',
        'name': 'Estudio Tafí SAS',
        'type': 'company',
        'doc_type': 'cuit',
        'doc_number': '30-60445512-6',
        'tax_condition': 'registered',
        'email': 'compras@estudiotafi.com',
        'phone': '+54 9 11 5555-4747',
        'address_line': 'Amenábar 1250',
        'city': 'Buenos Aires',
        'province': 'Buenos Aires',
        'postal_code': '1426',
        'country': 'Argentina',
        'note': 'Piden combos familiares para eventos corporativos.',
      },
      {
        'code': 'tech-riders',
        'name': 'Tech Riders SRL',
        'type': 'company',
        'doc_type': 'cuit',
        'doc_number': '30-68445512-2',
        'tax_condition': 'registered',
        'email': 'rrhh@techriders.com',
        'phone': '+54 9 11 5555-5151',
        'address_line': 'Gorostiaga 1800',
        'city': 'Buenos Aires',
        'province': 'Buenos Aires',
        'postal_code': '1426',
        'country': 'Argentina',
      },
      {
        'code': 'valen-club',
        'name': 'Club Social Valen',
        'type': 'company',
        'doc_type': 'cuit',
        'doc_number': '30-64445512-8',
        'tax_condition': 'monotax',
        'email': 'hola@clubvalen.com',
        'phone': '+54 9 11 5555-5150',
        'address_line': 'Montañeses 2100',
        'city': 'Buenos Aires',
        'province': 'Buenos Aires',
        'postal_code': '1428',
        'country': 'Argentina',
      },
      {
        'code': 'micaela-prado',
        'name': 'Micaela Prado',
        'type': 'individual',
        'doc_type': 'dni',
        'doc_number': '26321548',
        'tax_condition': 'consumer',
        'email': 'micaela.prado@demo.local',
        'phone': '+54 9 11 5555-1166',
        'address_line': 'Juramento 2900',
        'city': 'Buenos Aires',
        'province': 'Buenos Aires',
        'postal_code': '1428',
        'country': 'Argentina',
      },
    ],
    'users': [
      {'email': 'lapizza.owner@mirubro.local', 'name': 'LaPizza Owner', 'role': 'owner'},
      {'email': 'lapizza.manager@mirubro.local', 'name': 'LaPizza Manager', 'role': 'manager'},
      {'email': 'lapizza.cashier@mirubro.local', 'name': 'LaPizza Caja', 'role': 'cashier'},
      {'email': 'lapizza.kitchen@mirubro.local', 'name': 'LaPizza Cocina', 'role': 'kitchen'},
      {'email': 'lapizza.salon@mirubro.local', 'name': 'LaPizza Salon', 'role': 'salon'},
      {'email': 'lapizza.viewer@mirubro.local', 'name': 'LaPizza Viewer', 'role': 'viewer'},
    ],
  },
]

DEMO_BUSINESS_NAMES = [biz['name'] for biz in DEMO_BUSINESSES]
DEMO_USER_EMAILS = [user['email'] for biz in DEMO_BUSINESSES for user in biz['users']]

MANZANA_PRODUCTS = [
  {
    'name': 'Café Latte',
    'sku': 'LATTE',
    'price': Decimal('1800.00'),
    'cost': Decimal('700.00'),
    'stock_min': Decimal('12'),
    'initial_stock': Decimal('80'),
  },
  {
    'name': 'Espresso Doble',
    'sku': 'ESP-DBL',
    'price': Decimal('1200.00'),
    'cost': Decimal('400.00'),
    'stock_min': Decimal('8'),
    'initial_stock': Decimal('60'),
  },
  {
    'name': 'Medialuna Clásica',
    'sku': 'MED-CLA',
    'price': Decimal('450.00'),
    'cost': Decimal('150.00'),
    'stock_min': Decimal('30'),
    'initial_stock': Decimal('200'),
  },
  {
    'name': 'Medialuna Rellena',
    'sku': 'MED-REL',
    'price': Decimal('650.00'),
    'cost': Decimal('220.00'),
    'stock_min': Decimal('20'),
    'initial_stock': Decimal('120'),
  },
  {
    'name': 'Sandwich Veggie',
    'sku': 'SAND-VEG',
    'price': Decimal('2600.00'),
    'cost': Decimal('1100.00'),
    'stock_min': Decimal('8'),
    'initial_stock': Decimal('40'),
  },
  {
    'name': 'Tostado Jamón y Queso',
    'sku': 'SAND-TOS',
    'price': Decimal('2800.00'),
    'cost': Decimal('1200.00'),
    'stock_min': Decimal('10'),
    'initial_stock': Decimal('45'),
  },
  {
    'name': 'Jugo de Naranja',
    'sku': 'JUICE-NAR',
    'price': Decimal('1900.00'),
    'cost': Decimal('600.00'),
    'stock_min': Decimal('15'),
    'initial_stock': Decimal('70'),
  },
  {
    'name': 'Frappe Caramelo',
    'sku': 'FRAP-CAR',
    'price': Decimal('2300.00'),
    'cost': Decimal('900.00'),
    'stock_min': Decimal('10'),
    'initial_stock': Decimal('55'),
  },
  {
    'name': 'Brownie de Chocolate',
    'sku': 'BROWNIE',
    'price': Decimal('1500.00'),
    'cost': Decimal('500.00'),
    'stock_min': Decimal('12'),
    'initial_stock': Decimal('80'),
  },
  {
    'name': 'Alfajor Artesanal',
    'sku': 'ALFAJOR',
    'price': Decimal('1100.00'),
    'cost': Decimal('350.00'),
    'stock_min': Decimal('18'),
    'initial_stock': Decimal('90'),
  },
]

MANZANA_SAMPLE_SALES = [
  {
    'payment_method': 'cash',
    'notes': 'Venta mostrador - desayuno',
    'customer_slug': 'carolina-costa',
    'items': [
      {'sku': 'LATTE', 'quantity': Decimal('2')},
      {'sku': 'MED-CLA', 'quantity': Decimal('4')},
      {'sku': 'JUICE-NAR', 'quantity': Decimal('1')},
    ],
  },
  {
    'payment_method': 'card',
    'discount': Decimal('300.00'),
    'notes': 'Cliente habitual - pago con tarjeta',
    'customer_slug': 'lucia-y-sons',
    'items': [
      {'sku': 'SAND-TOS', 'quantity': Decimal('1')},
      {'sku': 'FRAP-CAR', 'quantity': Decimal('2')},
      {'sku': 'BROWNIE', 'quantity': Decimal('1')},
    ],
  },
  {
    'payment_method': 'transfer',
    'notes': 'Pedido corporativo sin cliente registrado',
    'items': [
      {'sku': 'SAND-VEG', 'quantity': Decimal('5')},
      {'sku': 'FRAP-CAR', 'quantity': Decimal('5')},
    ],
  },
]

MANZANA_FULL_CUSTOMER_SPECIALS = [
  {
    'code': 'consumidor-final',
    'name': 'Consumidor Final',
    'type': 'individual',
    'doc_type': '',
    'doc_number': '',
  },
  {
    'code': 'cliente-mostrador',
    'name': 'Cliente Mostrador',
    'type': 'individual',
    'doc_type': '',
    'doc_number': '',
    'note': 'Para ventas rápidas en mostrador sin datos adicionales.',
  },
  {
    'code': 'empresa-demo-sa',
    'name': 'Empresa Demo SA',
    'type': 'company',
    'doc_type': 'cuit',
    'doc_number': '30-99999999-7',
    'tax_condition': 'registered',
    'email': 'compras@empresademosa.com',
    'phone': '+54 9 11 5000-0000',
    'note': 'Cliente corporativo para escenarios B2B.',
  },
]

MANZANA_FULL_CUSTOMER_TARGET = 60
MANZANA_FULL_PRODUCT_TARGET = 110
MANZANA_FULL_SALES_DEFAULT = 480
MANZANA_DEFAULT_SALES_TARGET = 18

CUSTOMER_FIRST_NAMES = [
  'Camila', 'Sofía', 'Lucía', 'Martina', 'Elena', 'Malena', 'Emma', 'Isabella', 'Bautista', 'Felipe', 'Tomás', 'Mateo', 'Jorge',
  'Ramiro', 'Lautaro', 'Valentina', 'Joaquín', 'Ignacio', 'Agustina', 'Paula', 'Florencia', 'Bruno', 'Sebastián', 'Fabián',
  'Cecilia', 'Andrea', 'Chiara', 'Carla', 'Marcos', 'Hernán', 'Lara', 'Pilar', 'Franco', 'Lucas', 'Iara', 'Azul', 'Uma', 'Elías',
]

CUSTOMER_LAST_NAMES = [
  'Pérez', 'Rodríguez', 'Gómez', 'Fernández', 'Martínez', 'López', 'Sánchez', 'Gutiérrez', 'Arias', 'Peralta', 'Vega', 'Cáceres',
  'Paredes', 'Castro', 'Silva', 'Rojas', 'Romero', 'Medina', 'Soria', 'Toledo', 'Domínguez', 'Villar', 'Campos', 'Ortega',
  'Escobar', 'Benítez', 'Herrera', 'Navarro', 'Ponce', 'Salas', 'Suárez', 'Torres', 'Vallejos', 'Zárate', 'Quiroga', 'Maldonado',
]

CUSTOMER_NOTES = [
  'Prefiere envíos por la tarde.',
  'Solicita factura A cuando supera los $50.000.',
  'Atención especial: alérgico a frutos secos.',
  'Cliente fiel, usa cupones de descuento.',
  'Llamar antes de entregar.',
  'Deja reseñas en redes sociales.',
  'Solicita seguimiento de pedidos grandes.',
  'Habitual en días de semana a la mañana.',
]

PRODUCT_ADJECTIVES = [
  'Clásico', 'Premium', 'Orgánico', 'Intenso', 'Ligero', 'Artesanal', 'Casero', 'Gourmet', 'Gran Reserva', 'Fresco', 'Nocturno',
  'Express', 'Andino', 'Patagónico', 'Criollo', 'Mediterráneo', 'Vegano', 'Inspiración', 'Selecto', 'Auténtico',
]

PRODUCT_NOUNS = [
  'Blend', 'Latte', 'Cold Brew', 'Té Chai', 'Matcha', 'Medialuna', 'Budín', 'Cookie', 'Sandwich', 'Wrap', 'Ensalada', 'Bagel',
  'Tostado', 'Smoothie', 'Jugo', 'Limonada', 'Brownie', 'Crêpe', 'Tarta', 'Granola', 'Muffin', 'Bowl', 'Panini', 'Frappe',
]

PRODUCT_VARIANTS = ['Classic', 'XL', 'Zero', 'Noche', 'Matinal', 'Balcón', 'Campo', 'Studio', 'Express', 'Urbano']

PAYMENT_METHODS = ['cash', 'card', 'transfer', 'other']

SALE_NOTES = [
  'Venta demo generada automáticamente.',
  'Incluye combo desayuno.',
  'Cliente pidió detalle por email.',
  'Venta canal mostrador.',
  'Pedido con entrega same-day.',
  'Se aplicó descuento fidelidad.',
  'Ticket generado desde app móvil.',
]

CANCEL_REASONS = [
  'Cliente canceló luego de pagar.',
  'Error de carga, se rehace ticket.',
  'Stock insuficiente confirmado en depósito.',
  'Duplicado detectado por caja.',
]

DEFAULT_INVOICE_SERIES = [
  {'code': 'X', 'prefix': '0001', 'next_number': 1, 'is_active': True},
  {'code': 'B', 'prefix': '0002', 'next_number': 1, 'is_active': True},
]


class Command(BaseCommand):
  help = 'Seed demo businesses, users, and memberships for MiRubro.'

  def add_arguments(self, parser):
    parser.add_argument('--password', dest='password', default=DEFAULT_PASSWORD, help='Password to set for every demo user.')
    parser.add_argument('--reset', action='store_true', dest='reset', help='Delete existing demo data before recreating it.')
    parser.add_argument(
      '--full',
      '--full-manzana',
      action='store_true',
      dest='full_manzana',
      help='Genera un dataset completo para el negocio Manzana (clientes, productos, stock y ventas).',
    )
    parser.add_argument(
      '--full-sales',
      type=int,
      dest='full_sales',
      default=MANZANA_FULL_SALES_DEFAULT,
      help='Cantidad de ventas a generar cuando se usa --full (por defecto 480).',
    )

  def handle(self, *args, **options):
    password: str = options['password']
    reset: bool = options['reset']
    full_manzana: bool = options.get('full_manzana', False)
    full_sales: int = max(int(options.get('full_sales') or MANZANA_FULL_SALES_DEFAULT), 50)
    user_model = get_user_model()

    with transaction.atomic():
      if reset:
        self._reset_demo_data(user_model)

      summary: List[Dict[str, object]] = []
      for config in DEMO_BUSINESSES:
        business, subscription = self._ensure_business(config)
        self._ensure_invoice_series(business)
        if full_manzana and config['name'] == 'Manzana':
          customers = self._seed_manzana_full(business, config.get('customers', []), sales_target=full_sales)
        else:
          customers = self._ensure_customers(business, config.get('customers', []))
          if business.name == 'Manzana':
            products = self._ensure_manzana_products(business)
            self._seed_manzana_sales(business, products, customers)
        users_summary: List[Dict[str, str]] = []
        memberships_by_role: Dict[str, List[Membership]] = {}
        for user_config in config['users']:
          user = self._ensure_user(user_model, user_config, password)
          membership = self._ensure_membership(user, business, user_config['role'])
          memberships_by_role.setdefault(user_config['role'], []).append(membership)
          users_summary.append({'email': user.email, 'role': membership.role})
        self._seed_cash_activity(business, memberships_by_role)
        summary.append(
          {
            'business': business.name,
            'service': config['default_service'],
            'service_label': config['service_label'],
            'plan': subscription.plan,
            'users': users_summary,
          }
        )

    self._print_summary(summary, password)

  def _reset_demo_data(self, user_model) -> None:
    businesses = list(Business.objects.filter(name__in=DEMO_BUSINESS_NAMES))
    Membership.objects.filter(business__name__in=DEMO_BUSINESS_NAMES).delete()
    for business in businesses:
      self._purge_business_related_models(business)
    Business.objects.filter(pk__in=[biz.pk for biz in businesses]).delete()
    user_model.objects.filter(email__in=DEMO_USER_EMAILS).delete()
    self.stdout.write(self.style.WARNING('Existing demo businesses and users removed.'))

  def _ensure_business(self, config: Dict[str, object]):
    business, _ = Business.objects.get_or_create(
      name=config['name'],
      defaults={'default_service': config['default_service']},
    )
    if business.default_service != config['default_service']:
      business.default_service = config['default_service']
      business.save(update_fields=['default_service'])

    subscription, _ = Subscription.objects.get_or_create(
      business=business,
      defaults={'plan': config['plan'], 'status': ACTIVE_STATUS},
    )
    sub_fields: List[str] = []
    if subscription.plan != config['plan']:
      subscription.plan = config['plan']
      sub_fields.append('plan')
    if subscription.status != ACTIVE_STATUS:
      subscription.status = ACTIVE_STATUS
      sub_fields.append('status')
    if sub_fields:
      subscription.save(update_fields=sub_fields)
    return business, subscription

  def _ensure_user(self, user_model, user_config: Dict[str, str], password: str):
    email = user_config['email'].lower()
    full_name = user_config['name']
    first_name, last_name = self._split_name(full_name)
    username_field = getattr(user_model, 'USERNAME_FIELD', 'username')

    user = user_model.objects.filter(email__iexact=email).first()
    created = False
    if user is None:
      user_kwargs = {}
      if username_field != 'email':
        user_kwargs[username_field] = self._build_username(email)
      user = user_model(**user_kwargs)
      user.email = email
      created = True

    updated = created
    if user.email != email:
      user.email = email
      updated = True
    if user.first_name != first_name:
      user.first_name = first_name
      updated = True
    if user.last_name != last_name:
      user.last_name = last_name
      updated = True
    if not user.is_active:
      user.is_active = True
      updated = True
    if username_field != 'email':
      desired_username = self._build_username(email)
      if getattr(user, username_field, None) != desired_username:
        setattr(user, username_field, desired_username)
        updated = True

    user.set_password(password)
    updated = True

    if updated:
      user.save()

    return user

  def _ensure_membership(self, user, business, role: str):
    membership, created = Membership.objects.get_or_create(
      user=user,
      business=business,
      defaults={'role': role},
    )
    if not created and membership.role != role:
      membership.role = role
      membership.save(update_fields=['role'])
    return membership

  def _ensure_customers(self, business: Business, customers_config: List[Dict[str, object]]):
    customers_by_code = {}
    for entry in customers_config:
      code = entry.get('code') or slugify(entry.get('name', ''))
      if not entry.get('name'):
        continue
      lookup = {'business': business}
      doc_number = (entry.get('doc_number') or '').strip()
      doc_type = (entry.get('doc_type') or '').strip()
      if doc_number and doc_type:
        lookup.update({'doc_type': doc_type, 'doc_number': doc_number})
      else:
        lookup['name'] = entry['name']
      defaults = {
        'name': entry['name'],
        'type': entry.get('type') or 'individual',
        'tax_condition': entry.get('tax_condition', ''),
        'email': entry.get('email', ''),
        'phone': entry.get('phone', ''),
        'address_line': entry.get('address_line', ''),
        'city': entry.get('city', ''),
        'province': entry.get('province', ''),
        'postal_code': entry.get('postal_code', ''),
        'country': entry.get('country', ''),
        'note': entry.get('note', ''),
        'tags': entry.get('tags') or [],
        'is_active': True,
      }
      customer, _ = Customer.objects.update_or_create(defaults=defaults, **lookup)
      if code:
        customers_by_code[code] = customer
    return customers_by_code

  def _ensure_invoice_series(self, business: Business):
    series_records: List[InvoiceSeries] = []
    for config in DEFAULT_INVOICE_SERIES:
      series, created = InvoiceSeries.objects.get_or_create(
        business=business,
        code=config['code'],
        defaults={
          'prefix': config.get('prefix', ''),
          'next_number': config.get('next_number', 1),
          'is_active': config.get('is_active', True),
        },
      )
      update_fields: List[str] = []
      for field in ('prefix', 'next_number', 'is_active'):
        desired = config.get(field)
        if desired is not None and getattr(series, field) != desired:
          setattr(series, field, desired)
          update_fields.append(field)
      if update_fields:
        series.save(update_fields=update_fields)
      series_records.append(series)

    if not any(series.is_active for series in series_records):
      target = series_records[0] if series_records else InvoiceSeries.objects.create(business=business, code='X')
      if not target.is_active:
        target.is_active = True
        target.save(update_fields=['is_active'])

    return InvoiceSeries.objects.filter(business=business).order_by('code')

  def _print_summary(self, summary: List[Dict[str, object]], password: str) -> None:
    if not summary:
      self.stdout.write('No demo data created.')
      return

    label_map = {choice[0]: choice[1] for choice in BusinessPlan.choices}
    self.stdout.write('')
    self.stdout.write(self.style.SUCCESS('Demo businesses ready:'))
    for entry in summary:
      plan_value = entry['plan']
      plan_label = label_map.get(plan_value, str(plan_value))
      self.stdout.write(f"- {entry['business']} · servicio {entry['service_label']} · plan {plan_label}")
      for user in entry['users']:
        self.stdout.write(f"    {user['role']:<8} {user['email']}  contraseña: {password}")
    self.stdout.write('')
    self.stdout.write(f'Ingresá en: {LOGIN_URL}')

  def _split_name(self, full_name: str):
    parts = full_name.strip().split(' ', 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ''
    return first_name, last_name

  def _build_username(self, email: str) -> str:
    local_part = email.split('@')[0]
    candidate = slugify(local_part)
    return candidate or local_part

  def _ensure_manzana_products(self, business: Business):
    products_by_sku: Dict[str, Product] = {}
    for config in MANZANA_PRODUCTS:
      product, _ = Product.objects.update_or_create(
        business=business,
        sku=config['sku'],
        defaults={
          'name': config['name'],
          'price': config['price'],
          'cost': config['cost'],
          'stock_min': config['stock_min'],
          'is_active': True,
        },
      )
      stock, created = ProductStock.objects.get_or_create(
        business=business,
        product=product,
        defaults={'quantity': config['initial_stock']},
      )
      if not created and stock.quantity != config['initial_stock']:
        stock.quantity = config['initial_stock']
        stock.save(update_fields=['quantity'])
      products_by_sku[config['sku']] = product
    return products_by_sku

  def _seed_manzana_sales(self, business: Business, products_by_sku: Dict[str, Product], customers_by_code: Dict[str, Customer]):
    if Sale.objects.filter(business=business).exists():
      return
    templates = MANZANA_SAMPLE_SALES or []
    if not templates:
      return
    total_target = max(len(templates), MANZANA_DEFAULT_SALES_TARGET)
    now = timezone.now()
    created = 0
    iteration = 0
    while created < total_target:
      sale_config = templates[iteration % len(templates)]
      items_payload = []
      for item in sale_config['items']:
        product = products_by_sku.get(item['sku'])
        if not product:
          continue
        quantity = item['quantity']
        if random.random() < 0.25:
          quantity = quantity + Decimal(random.randint(1, 2))
        items_payload.append(
          {
            'product_id': str(product.id),
            'quantity': str(quantity),
            'unit_price': str(item.get('unit_price', product.price)),
          }
        )
      if not items_payload:
        iteration += 1
        continue
      discount = sale_config.get('discount', Decimal('0'))
      if discount == Decimal('0') and random.random() < 0.2:
        discount = Decimal(random.randint(50, 250))
      payload = {
        'payment_method': sale_config['payment_method'],
        'discount': str(discount),
        'notes': sale_config.get('notes', ''),
        'items': items_payload,
      }
      slug = sale_config.get('customer_slug')
      if slug and slug in customers_by_code:
        payload['customer_id'] = str(customers_by_code[slug].id)

      serializer = SaleCreateSerializer(data=payload, context={'business': business})
      serializer.is_valid(raise_exception=True)
      sale = serializer.save()
      day_block = iteration // len(templates)
      created_at = now - timedelta(days=(day_block * 2) + random.randint(0, 1), hours=random.randint(0, 8), minutes=random.randint(0, 55))
      Sale.objects.filter(pk=sale.pk).update(created_at=created_at, updated_at=created_at)
      created += 1
      iteration += 1

  def _seed_cash_activity(self, business: Business, memberships_by_role: Dict[str, List[Membership]]):
    if Payment.objects.filter(business=business).exists():
      return
    sales = list(
      Sale.objects.filter(business=business, status=Sale.Status.COMPLETED)
      .order_by('-created_at')[:80]
    )
    if not sales:
      return
    registers = self._ensure_cash_registers(business)
    if not registers:
      return
    operator_membership = self._pick_operator_membership(memberships_by_role)
    operator_user = getattr(operator_membership, 'user', None)
    sessions: List[CashSession] = []
    now = timezone.now()
    for index, register in enumerate(registers[:2]):
      session = CashSession.objects.create(
        business=business,
        register=register,
        opened_by=operator_user,
        opening_cash_amount=Decimal(random.randint(2000, 8000)),
      )
      opened_at = now - timedelta(days=index + 1)
      CashSession.objects.filter(pk=session.pk).update(opened_at=opened_at)
      session.refresh_from_db()
      sessions.append(session)
    if not sessions:
      return
    payment_methods = [choice for choice, _ in Payment.Method.choices]
    for idx, sale in enumerate(sales):
      total = (sale.total or Decimal('0')).quantize(Decimal('0.01'))
      if total <= 0:
        continue
      session = sessions[idx % len(sessions)]
      splits = [total]
      if total > Decimal('2000') and random.random() < 0.35:
        first = (total * Decimal(random.uniform(0.4, 0.7))).quantize(Decimal('0.01'))
        second = total - first
        if second > Decimal('0'):
          splits = [first, second]
      for amount in splits:
        if amount <= 0:
          continue
        method = Payment.Method.CASH if random.random() < 0.55 else random.choice(payment_methods)
        reference = '' if method == Payment.Method.CASH else f"REF-{sale.number}-{random.randint(100, 999)}"
        Payment.objects.create(
          business=business,
          sale=sale,
          session=session,
          method=method,
          amount=amount,
          reference=reference,
          created_by=operator_user,
        )
    for session in sessions:
      self._create_cash_movements(session, operator_user)
      totals = compute_session_totals(session)
      expected = totals['cash_expected_total']
      diff = Decimal(random.randint(-200, 200)) / Decimal('100')
      closing_amount = (expected + diff).quantize(Decimal('0.01')) if expected is not None else None
      session.expected_cash_total = expected
      session.closing_cash_counted = closing_amount if closing_amount and closing_amount > 0 else expected
      session.difference_amount = (session.closing_cash_counted or Decimal('0')) - (expected or Decimal('0'))
      session.status = CashSession.Status.CLOSED
      session.closing_note = 'Cierre demo automatizado'
      session.closed_at = session.opened_at + timedelta(hours=12)
      if operator_user:
        session.closed_by = operator_user
      update_fields = [
        'expected_cash_total',
        'closing_cash_counted',
        'difference_amount',
        'status',
        'closing_note',
        'closed_at',
      ]
      if operator_user:
        update_fields.append('closed_by')
      session.save(update_fields=update_fields)

  def _ensure_cash_registers(self, business: Business) -> List[CashRegister]:
    registers: List[CashRegister] = []
    for name in ('Caja Principal', 'Caja Secundaria'):
      register, _ = CashRegister.objects.get_or_create(
        business=business,
        name=name,
        defaults={'is_active': True},
      )
      if not register.is_active:
        register.is_active = True
        register.save(update_fields=['is_active'])
      registers.append(register)
    return registers

  def _pick_operator_membership(self, memberships_by_role: Dict[str, List[Membership]]) -> Optional[Membership]:
    for role in ('cashier', 'manager', 'owner', 'staff'):
      role_members = memberships_by_role.get(role)
      if role_members:
        return role_members[0]
    for members in memberships_by_role.values():
      if members:
        return members[0]
    return None

  def _create_cash_movements(self, session: CashSession, operator_user):
    CashMovement.objects.create(
      business=session.business,
      session=session,
      movement_type=CashMovement.MovementType.IN,
      category=CashMovement.Category.DEPOSIT,
      method=Payment.Method.CASH,
      amount=Decimal(random.randint(200, 800)),
      note='Ingreso demo',
      created_by=operator_user,
    )
    CashMovement.objects.create(
      business=session.business,
      session=session,
      movement_type=CashMovement.MovementType.OUT,
      category=CashMovement.Category.WITHDRAW,
      method=Payment.Method.CASH,
      amount=Decimal(random.randint(100, 500)),
      note='Retiro demo',
      created_by=operator_user,
    )

  def _seed_manzana_full(self, business: Business, base_customers_config: List[Dict[str, object]], *, sales_target: int):
    self.stdout.write(self.style.WARNING('Generando dataset completo para Manzana...'))
    self._purge_manzana_data(business)
    self._ensure_invoice_series(business)
    combined_customers = list(base_customers_config or []) + MANZANA_FULL_CUSTOMER_SPECIALS
    customers = self._ensure_customers(business, combined_customers)
    customers.update(self._generate_random_customers(business, customers, MANZANA_FULL_CUSTOMER_TARGET))
    products = self._generate_random_products(business, MANZANA_FULL_PRODUCT_TARGET)
    self._seed_inventory_for_products(business, products)
    generated_sales = self._create_sales_dataset(business, products, list(customers.values()), sales_target)
    self.stdout.write(
      self.style.SUCCESS(
        f"Manzana lista: {len(customers)} clientes, {len(products)} productos y {generated_sales} ventas demo.",
      )
    )
    return customers

  def _purge_manzana_data(self, business: Business) -> None:
    self._purge_business_related_models(business)

  def _purge_business_related_models(self, business: Business) -> None:
    Payment.objects.filter(business=business).delete()
    CashMovement.objects.filter(business=business).delete()
    CashSession.objects.filter(business=business).delete()
    CashRegister.objects.filter(business=business).delete()
    Invoice.objects.filter(business=business).delete()
    InvoiceSeries.objects.filter(business=business).delete()
    Sale.objects.filter(business=business).delete()
    StockMovement.objects.filter(business=business).delete()
    ProductStock.objects.filter(business=business).delete()
    Product.objects.filter(business=business).delete()
    Customer.objects.filter(business=business).delete()

  def _generate_random_customers(
    self,
    business: Business,
    existing_map: Dict[str, Customer],
    target_total: int,
  ) -> Dict[str, Customer]:
    created: Dict[str, Customer] = {}
    used_codes = {key for key in existing_map.keys() if key}
    used_names = {customer.name.lower() for customer in existing_map.values()}

    while len(existing_map) + len(created) < target_total:
      first_name = random.choice(CUSTOMER_FIRST_NAMES)
      last_name = random.choice(CUSTOMER_LAST_NAMES)
      name = f"{first_name} {last_name}"
      if name.lower() in used_names:
        name = f"{name} {random.randint(1, 99)}"
      code_base = slugify(name) or f"cliente-{random.randint(1000, 9999)}"
      code = code_base
      suffix = 1
      while not code or code in used_codes:
        code = f"{code_base}-{suffix}"
        suffix += 1
      used_codes.add(code)
      used_names.add(name.lower())

      doc_type, doc_number = self._random_document()
      email = ''
      if random.random() < 0.7:
        email = f"{code.replace('-', '.')[:32]}@clientesdemo.com"
      phone = ''
      if random.random() < 0.6:
        phone = f"+54 9 11 {random.randint(4000, 9999):04d}-{random.randint(1000, 9999):04d}"
      note = random.choice(CUSTOMER_NOTES) if random.random() < 0.4 else ''

      customer = Customer.objects.create(
        business=business,
        name=name,
        type='company' if random.random() < 0.18 else 'individual',
        doc_type=doc_type,
        doc_number=doc_number,
        tax_condition=random.choice(['consumer', 'monotax', 'registered', 'exempt']),
        email=email,
        phone=phone,
        address_line='Av. Demo ' + str(random.randint(100, 900)) if random.random() < 0.5 else '',
        city='Buenos Aires',
        province='Buenos Aires',
        postal_code=str(1000 + random.randint(0, 200)),
        country='Argentina',
        note=note,
        tags=[],
        is_active=True,
      )
      created[code] = customer
    return created

  def _random_document(self):
    roll = random.random()
    if roll < 0.55:
      return 'dni', str(random.randint(20000000, 48000000))
    if roll < 0.75:
      middle = random.randint(10000000, 99999999)
      suffix = random.randint(0, 9)
      return 'cuit', f"30-{middle:08d}-{suffix}"
    return '', ''

  def _generate_random_products(self, business: Business, target_count: int):
    products: List[Dict[str, object]] = []
    used_skus = set()
    for index in range(target_count):
      base_name = f"{random.choice(PRODUCT_ADJECTIVES)} {random.choice(PRODUCT_NOUNS)}"
      if random.random() < 0.35:
        base_name = f"{base_name} {random.choice(PRODUCT_VARIANTS)}"
      sku_candidate = slugify(base_name).upper().replace('-', '')[:10]
      if not sku_candidate:
        sku_candidate = f"SKU{index:04d}"
      while sku_candidate in used_skus:
        sku_candidate = f"SKU{random.randint(1000, 9999)}"
      used_skus.add(sku_candidate)

      cost = self._money(250, 3800)
      margin = Decimal(str(random.uniform(1.2, 2.7)))
      price = (cost * margin).quantize(Decimal('0.01'))
      stock_min = Decimal(random.randint(4, 35))
      is_active = random.random() > 0.08

      product = Product.objects.create(
        business=business,
        name=base_name,
        sku=sku_candidate,
        price=price,
        cost=cost,
        stock_min=stock_min,
        is_active=is_active,
      )
      initial_stock = Decimal(random.randint(30, 220))
      products.append({'product': product, 'initial_stock': initial_stock})
    return products

  def _seed_inventory_for_products(self, business: Business, products: List[Dict[str, object]]) -> None:
    for entry in products:
      quantity = entry['initial_stock']
      if quantity <= 0:
        continue
      register_stock_movement(
        business=business,
        product=entry['product'],
        movement_type=StockMovement.MovementType.IN,
        quantity=quantity,
        note='Stock inicial demo extendido',
      )

    zero_candidates = random.sample(products, min(18, len(products)))
    for entry in zero_candidates:
      stock = ensure_stock_record(business, entry['product'])
      if stock.quantity <= 0:
        continue
      register_stock_movement(
        business=business,
        product=entry['product'],
        movement_type=StockMovement.MovementType.WASTE,
        quantity=stock.quantity,
        note='Ajuste inventario: sin stock',
      )

    remaining = [entry for entry in products if entry not in zero_candidates]
    low_candidates = random.sample(remaining, min(22, len(remaining)))
    for entry in low_candidates:
      target = max(Decimal('1'), entry['product'].stock_min / 2)
      register_stock_movement(
        business=business,
        product=entry['product'],
        movement_type=StockMovement.MovementType.ADJUST,
        quantity=target.quantize(Decimal('0.01')),
        note='Reconteo: stock crítico',
      )

    adjustment_pool = random.sample(products, min(30, len(products)))
    for entry in adjustment_pool:
      product = entry['product']
      stock = ensure_stock_record(business, product)
      if random.random() < 0.5:
        qty = Decimal(random.randint(5, 18))
        register_stock_movement(
          business=business,
          product=product,
          movement_type=StockMovement.MovementType.IN,
          quantity=qty,
          note='Reposición semanal demo',
        )
      else:
        if stock.quantity <= 0:
          continue
        qty = min(stock.quantity, Decimal(random.randint(2, 10)))
        register_stock_movement(
          business=business,
          product=product,
          movement_type=StockMovement.MovementType.WASTE,
          quantity=qty,
          note='Merma por rotura demo',
        )

  def _create_sales_dataset(
    self,
    business: Business,
    product_entries: List[Dict[str, object]],
    customers: List[Customer],
    sales_target: int,
  ) -> int:
    product_pool: List[Dict[str, object]] = []
    for entry in product_entries:
      product = entry['product']
      stock_record = ensure_stock_record(business, product)
      if stock_record.quantity <= 0:
        continue
      if not product.is_active:
        continue
      product_pool.append({'product': product, 'available': stock_record.quantity})

    if not product_pool:
      return 0

    now = timezone.now()
    generated = 0
    for _ in range(sales_target):
      sale_date = now - timedelta(days=random.randint(0, 90), minutes=random.randint(0, 600))
      items = self._build_sale_items(product_pool)
      if not items:
        break
      subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
      if subtotal <= 0:
        continue
      discount = Decimal('0')
      if random.random() < 0.35:
        max_discount = (subtotal * Decimal('0.18')).quantize(Decimal('0.01'))
        discount = (max_discount * Decimal(str(random.random()))).quantize(Decimal('0.01'))

      payload = {
        'payment_method': random.choice(PAYMENT_METHODS),
        'discount': str(discount),
        'notes': random.choice(SALE_NOTES) if random.random() < 0.6 else '',
        'items': [
          {
            'product_id': str(item['product'].id),
            'quantity': str(item['quantity']),
            'unit_price': str(item['unit_price']),
          }
          for item in items
        ],
      }

      if customers and random.random() < 0.7:
        payload['customer_id'] = str(random.choice(customers).id)

      serializer = SaleCreateSerializer(data=payload, context={'business': business})
      serializer.is_valid(raise_exception=True)
      sale = serializer.save()
      Sale.objects.filter(pk=sale.pk).update(created_at=sale_date, updated_at=sale_date)

      for item in items:
        item['entry']['available'] -= item['quantity']
      generated += 1

      if random.random() < 0.12:
        cancel_serializer = SaleCancelSerializer(
          data={'reason': random.choice(CANCEL_REASONS)},
          context={'sale': sale, 'user': None},
        )
        cancel_serializer.is_valid(raise_exception=True)
        cancel_serializer.save()
    return generated

  def _build_sale_items(self, product_pool: List[Dict[str, object]]):
    candidates = [entry for entry in product_pool if entry['available'] >= Decimal('1')]
    if not candidates:
      return []
    count = random.randint(1, min(5, len(candidates)))
    selected = random.sample(candidates, count)
    items = []
    for entry in selected:
      max_units = int(entry['available'])
      if max_units <= 0:
        continue
      quantity = Decimal(random.randint(1, min(5, max_units)))
      items.append({'product': entry['product'], 'quantity': quantity, 'unit_price': entry['product'].price, 'entry': entry})
    return items

  def _money(self, minimum: float, maximum: float) -> Decimal:
    return Decimal(str(random.uniform(minimum, maximum))).quantize(Decimal('0.01'))
