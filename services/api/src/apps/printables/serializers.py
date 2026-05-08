"""
Serializers para el módulo Printables — Carteles y Etiquetas.
"""
from __future__ import annotations

from rest_framework import serializers

from .constants import (
    BORDER_STYLES,
    CARD_SIZE_TOLERANCE,
    FONT_PRESETS,
    FONT_SIZES,
    LAYOUT_STYLES,
    LOGO_POSITIONS,
    LOGO_SIZES,
    LOGO_VARIANTS,
    MAX_COPIES_PER_ITEM,
    MAX_ITEMS,
    PAPER_SIZES,
    PRINTABLE_TYPES,
    TEMPLATE_CODES,
    TYPE_TEMPLATE_MAP,
    VALID_CARD_SIZES,
)


class CardSizeSerializer(serializers.Serializer):
    width_cm = serializers.FloatField(min_value=0.1, max_value=50.0)
    height_cm = serializers.FloatField(min_value=0.1, max_value=50.0)

    def validate(self, attrs):
        w = attrs['width_cm']
        h = attrs['height_cm']
        for allowed in VALID_CARD_SIZES:
            if (
                abs(allowed['width_cm'] - w) <= CARD_SIZE_TOLERANCE
                and abs(allowed['height_cm'] - h) <= CARD_SIZE_TOLERANCE
            ):
                return attrs
        codes = ', '.join(
            f"{s['code']} ({s['width_cm']}×{s['height_cm']} cm)"
            for s in VALID_CARD_SIZES
        )
        raise serializers.ValidationError(
            f'Tamaño de card no permitido. Opciones válidas: {codes}.'
        )


class PrintableItemSerializer(serializers.Serializer):
    product_id  = serializers.UUIDField(required=False, allow_null=True, default=None)
    title       = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=300, required=False, allow_blank=True, default='')
    price       = serializers.CharField(max_length=30, required=False, allow_blank=True, default='')
    old_price   = serializers.CharField(max_length=30, required=False, allow_blank=True, default='')
    promo_text  = serializers.CharField(max_length=60, required=False, allow_blank=True, default='')
    copies      = serializers.IntegerField(min_value=1, max_value=MAX_COPIES_PER_ITEM, default=1)


class GeneratePDFSerializer(serializers.Serializer):
    type          = serializers.ChoiceField(choices=PRINTABLE_TYPES)
    template_code = serializers.ChoiceField(choices=TEMPLATE_CODES)
    paper_size    = serializers.ChoiceField(choices=PAPER_SIZES, default='A4')
    card_size     = CardSizeSerializer()
    logo_variant  = serializers.ChoiceField(choices=LOGO_VARIANTS, default='none')
    include_logo  = serializers.BooleanField(default=False)
    include_price = serializers.BooleanField(default=True)
    show_cut_lines = serializers.BooleanField(default=True)
    items         = PrintableItemSerializer(many=True, min_length=1, max_length=MAX_ITEMS)
    # Phase 4: opciones de diseño visual (todos opcionales con defaults)
    layout_style  = serializers.ChoiceField(choices=LAYOUT_STYLES, default='centered_product')
    font_preset   = serializers.ChoiceField(choices=FONT_PRESETS, default='bold')
    border_style  = serializers.ChoiceField(choices=BORDER_STYLES, default='none')
    border_color  = serializers.CharField(max_length=7, default='#000000')
    border_width  = serializers.IntegerField(min_value=0, max_value=8, default=2)
    border_radius = serializers.IntegerField(min_value=0, max_value=20, default=0)
    logo_size     = serializers.ChoiceField(choices=LOGO_SIZES, default='medium')
    logo_position = serializers.ChoiceField(choices=LOGO_POSITIONS, default='top_center')
    # Phase 5: control fino de tipografía y padding
    inner_border_padding_cm = serializers.FloatField(min_value=0, max_value=2, default=0.3)
    title_font_size         = serializers.ChoiceField(choices=FONT_SIZES, default='medium')
    price_font_size         = serializers.ChoiceField(choices=FONT_SIZES, default='large')
    secondary_font_size     = serializers.ChoiceField(choices=FONT_SIZES, default='small')
    # Phase 6: marco de contenido
    content_frame_enabled    = serializers.BooleanField(default=True)
    content_frame_color      = serializers.CharField(max_length=7, default='#000000')
    content_frame_width      = serializers.IntegerField(min_value=0, max_value=8, default=2)
    content_frame_padding_cm = serializers.FloatField(min_value=0, max_value=2, default=0.4)
    content_inner_padding_cm = serializers.FloatField(min_value=0, max_value=2, default=0.3)
    # Phase 7: transformación de texto
    text_transform = serializers.ChoiceField(choices=['none', 'uppercase'], default='none')
    # Phase 9: colores y espaciado
    header_text_color = serializers.CharField(max_length=7, default='#DC2626')
    title_text_color  = serializers.CharField(max_length=7, default='#111827')
    price_text_color  = serializers.CharField(max_length=7, default='#000000')
    price_gap_pt      = serializers.FloatField(min_value=0, max_value=60, default=10)
    # Phase 8: zona superior configurable
    header_content_type = serializers.ChoiceField(
        choices=['logo', 'highlight_text', 'none'],
        required=False,
        allow_null=True,
        default=None,
    )
    header_text = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default='',
    )

    def validate(self, attrs):
        import re
        printable_type = attrs.get('type')
        template_code  = attrs.get('template_code')
        allowed = TYPE_TEMPLATE_MAP.get(printable_type, [])
        if template_code not in allowed:
            raise serializers.ValidationError({
                'template_code': (
                    f"template_code '{template_code}' no es válido para type '{printable_type}'. "
                    f"Opciones: {', '.join(allowed)}."
                )
            })
        # Validar border_color cuando border_style='custom'
        if attrs.get('border_style') == 'custom':
            color = attrs.get('border_color', '')
            if not re.match(r'^#[0-9A-Fa-f]{6}$', color):
                raise serializers.ValidationError({
                    'border_color': (
                        "border_color debe ser un color hex válido (ej. #FF0000) "
                        "cuando border_style='custom'."
                    )
                })
        # Validar content_frame_color cuando content_frame_enabled=True
        if attrs.get('content_frame_enabled', True):
            fc = attrs.get('content_frame_color', '#000000')
            if not re.match(r'^#[0-9A-Fa-f]{6}$', fc):
                raise serializers.ValidationError({
                    'content_frame_color': (
                        "content_frame_color debe ser un color hex válido (ej. #FF0000)."
                    )
                })
        # Validar colores Phase 9
        for field in ('header_text_color', 'title_text_color', 'price_text_color'):
            val = attrs.get(field, '')
            if val and not re.match(r'^#[0-9A-Fa-f]{6}$', val):
                raise serializers.ValidationError({
                    field: f"{field} debe ser un color hex válido (ej. #DC2626)."
                })
        return attrs
