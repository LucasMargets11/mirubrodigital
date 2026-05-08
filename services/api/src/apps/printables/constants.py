"""
Constantes para el módulo Printables — Carteles y Etiquetas.
"""

# Tamaños de card permitidos (en centímetros)
VALID_CARD_SIZES = [
    {'code': '5x3',  'width_cm': 5.0,  'height_cm': 3.0},
    {'code': '6x4',  'width_cm': 6.0,  'height_cm': 4.0},
    {'code': '7x5',  'width_cm': 7.0,  'height_cm': 5.0},
    {'code': '10x7', 'width_cm': 10.0, 'height_cm': 7.0},
    {'code': '12x8', 'width_cm': 12.0, 'height_cm': 8.0},
    {'code': '15x10','width_cm': 15.0, 'height_cm': 10.0},
    {'code': 'a6',   'width_cm': 10.5, 'height_cm': 14.8},
    {'code': 'a5',   'width_cm': 14.8, 'height_cm': 21.0},
    {'code': 'a4',   'width_cm': 21.0, 'height_cm': 29.7},
]

# Tolerancia en cm para comparación de medidas flotantes
CARD_SIZE_TOLERANCE = 0.05

# Márgenes de página en centímetros
PAGE_MARGIN_CM = 1.0

# Separación entre cards en centímetros
CARD_GAP_CM = 0.3

# Templates disponibles
TEMPLATE_CODES = [
    'product_price_simple',
    'promo_offer',
    'promo_discount',
    'promo_2x1',
    'promo_combo',
    'promo_clearance',
    'promo_weekly',
]

# Tipos disponibles
PRINTABLE_TYPES = ['product', 'promotion']

# Mapa de tipos → templates válidos
TYPE_TEMPLATE_MAP = {
    'product':   ['product_price_simple'],
    'promotion': [
        'promo_offer',
        'promo_discount',
        'promo_2x1',
        'promo_combo',
        'promo_clearance',
        'promo_weekly',
    ],
}

# Tamaños de papel disponibles
PAPER_SIZES = ['A4']

# Variantes de logo disponibles
LOGO_VARIANTS = ['none', 'horizontal', 'square', 'default']

# Máx de items en el payload (antes de expandir copies)
MAX_ITEMS = 50

# Máx de copias por item
MAX_COPIES_PER_ITEM = 20

# ── Phase 4: Diseño visual ────────────────────────────────────────────────────

# Estilos de layout de la card
LAYOUT_STYLES = [
    'centered_product',
    'price_focus',
    'promo_badge',
    'framed_label',
    'minimal_label',
]

# Presets de tipografía
FONT_PRESETS = ['bold', 'regular', 'elegant', 'condensed']

# Estilos de borde
BORDER_STYLES = ['none', 'black', 'accent', 'custom']

# Tamaños de logo
LOGO_SIZES = ['small', 'medium', 'large', 'xlarge']

# Posiciones de logo
LOGO_POSITIONS = ['top_center', 'top_left']

# ── Phase 5: control fino de tipografía y padding ─────────────────────────────

# Niveles de tamaño tipográfico (título, precio, secundario)
FONT_SIZES = ['small', 'medium', 'large', 'xlarge']
