"""
Preset logic for menu layout blocks.

Two built-in presets:
  - drinks_first: Beverages → Food → Desserts
  - food_first:   Food → Beverages → Desserts
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import MenuLayoutBlock, MenuCategory

# ---------------------------------------------------------------------------
# Keyword groups used to auto-assign categories to blocks
# ---------------------------------------------------------------------------

_DRINK_KEYWORDS = {
    'cocktail', 'cóctel', 'coctel', 'trago', 'bebida', 'cerveza', 'vino',
    'soft drink', 'gaseosa', 'jugo', 'cafe', 'café', 'bakery', 'brunch',
    'aperitivo', 'fernet', 'whisky', 'vodka', 'gin', 'agua', 'soda',
    'limonada', 'licuado', 'infusion', 'infusión', 'té', 'te',
}

_DESSERT_KEYWORDS = {
    'postre', 'dulce', 'torta', 'helado', 'mousse', 'flan', 'brownie',
    'cookie', 'cheesecake', 'tiramisu', 'tiramisú', 'macarron', 'macarrón',
}

_FOOD_KEYWORDS = {
    'entrada', 'burger', 'hamburguesa', 'sandwich', 'sándwich', 'wrap',
    'ensalada', 'pizza', 'comida', 'plato', 'pastas', 'carnes', 'pollo',
    'milanesa', 'taco', 'burritos', 'empanada', 'brochette', 'wok',
    'sushi', 'ceviche', 'paella', 'risotto', 'grill',
}


def _category_group(name: str) -> str:
    """Return 'drink', 'dessert', or 'food' for a category name."""
    lower = name.lower()
    for kw in _DRINK_KEYWORDS:
        if kw in lower:
            return 'drink'
    for kw in _DESSERT_KEYWORDS:
        if kw in lower:
            return 'dessert'
    return 'food'


def apply_preset(business, template: str) -> None:
    """
    Delete existing layout blocks for *business* and build fresh ones from the
    named preset.  Categories not matched by keywords go into 'food'.

    Args:
        business: Business model instance
        template: one of 'drinks_first' | 'food_first'
    """
    from .models import MenuCategory, MenuLayoutBlock, MenuLayoutBlockCategory

    # Remove current layout
    MenuLayoutBlock.objects.filter(business=business).delete()

    categories = list(
        MenuCategory.objects.filter(business=business, is_active=True).order_by('position', 'name')
    )

    groups: dict[str, list[MenuCategory]] = {'drink': [], 'food': [], 'dessert': []}
    for cat in categories:
        g = _category_group(cat.name)
        groups[g].append(cat)

    if template == 'drinks_first':
        block_order = [
            ('Bebidas', 'drink'),
            ('Comida', 'food'),
            ('Postres', 'dessert'),
        ]
    else:  # food_first
        block_order = [
            ('Comida', 'food'),
            ('Bebidas', 'drink'),
            ('Postres', 'dessert'),
        ]

    for blk_pos, (title, group_key) in enumerate(block_order):
        cats_for_block = groups.get(group_key, [])
        block = MenuLayoutBlock.objects.create(
            business=business,
            title=title,
            position=blk_pos,
            layout='stack',
            columns_desktop=2 if group_key == 'drink' else 3,
            columns_tablet=2,
            columns_mobile=1,
        )
        for cat_pos, cat in enumerate(cats_for_block):
            MenuLayoutBlockCategory.objects.create(
                block=block,
                category=cat,
                position=cat_pos,
            )
