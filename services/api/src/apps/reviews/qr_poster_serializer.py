"""
Serializer para el endpoint POST /api/v1/reviews/qr-posters/generate-pdf/

Valida el payload de generación de carteles QR de Reseñas PRO.
"""
from __future__ import annotations

import re

from rest_framework import serializers

# ── Whitelists ────────────────────────────────────────────────────────────────

VALID_POSTER_SIZES = (
    'a4_portrait',
    'a4_landscape',
    'a5_portrait',
    'half_a4',
    'desk_card',
    'sticker_square',
)

VALID_TEMPLATE_CODES = (
    'simple_centered',
    'qr_left',
    'bold_cta',
)

VALID_LOGO_VARIANTS = (
    'default',
    'horizontal',
    'square',
    'none',
)

VALID_LOGO_POSITIONS = (
    'top-left',
    'top-center',
    'top-right',
    'bottom-left',
    'bottom-center',
    'bottom-right',
    'middle-left',
    'middle-right',
)

VALID_BACKGROUND_MODES = (
    'color',
    'image',
)

VALID_TITLE_FONTS = (
    'sans_bold',
    'serif_bold',
    'mono_bold',
)

VALID_FONT_FAMILIES = (
    'cinzel',
    'montserrat',
    'poppins',
    'raleway',
    'playfair_display',
    'work_sans',
    'lato',
    'oswald',
    'cormorant_garamond',
    'libre_baskerville',
)

VALID_FONT_WEIGHTS = (
    'regular',
    'bold',
    'black',
)

VALID_OUTLINE_WIDTHS = (0.25, 0.4, 0.6, 0.8)

_HEX_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')


# ── Serializer ────────────────────────────────────────────────────────────────

class GenerateQrPosterSerializer(serializers.Serializer):
    poster_size = serializers.ChoiceField(
        choices=VALID_POSTER_SIZES,
    )
    template_code = serializers.ChoiceField(
        choices=VALID_TEMPLATE_CODES,
    )
    main_text = serializers.CharField(
        max_length=80,
        allow_blank=False,
    )
    subtitle = serializers.CharField(
        max_length=80,
        allow_blank=True,
        required=False,
        default='',
    )
    include_logo = serializers.BooleanField(
        default=True,
    )
    logo_variant = serializers.ChoiceField(
        choices=VALID_LOGO_VARIANTS,
        default='default',
    )
    logo_position = serializers.ChoiceField(
        choices=VALID_LOGO_POSITIONS,
        default='top-center',
        required=False,
    )
    logo_margin_mm = serializers.FloatField(
        default=8.0,
        required=False,
        min_value=0.0,
        max_value=40.0,
    )
    background_color = serializers.CharField(
        default='#FFFFFF',
        required=False,
    )
    background_mode = serializers.ChoiceField(
        choices=VALID_BACKGROUND_MODES,
        default='color',
    )
    title_font = serializers.ChoiceField(
        choices=VALID_TITLE_FONTS,
        default='sans_bold',
        required=False,
    )
    font_family = serializers.ChoiceField(
        choices=VALID_FONT_FAMILIES,
        default=None,
        required=False,
        allow_null=True,
    )
    font_weight = serializers.ChoiceField(
        choices=VALID_FONT_WEIGHTS,
        default=None,
        required=False,
        allow_null=True,
    )
    main_text_color = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default=None,
    )
    subtitle_text_color = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default=None,
    )
    main_text_outline_enabled = serializers.BooleanField(
        default=False,
        required=False,
    )
    main_text_outline_color = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default='#000000',
    )
    subtitle_text_outline_enabled = serializers.BooleanField(
        default=False,
        required=False,
    )
    subtitle_text_outline_color = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default='#000000',
    )
    text_outline_width = serializers.FloatField(
        default=0.4,
        required=False,
    )
    qr_scale = serializers.ChoiceField(
        choices=('small', 'medium', 'large'),
        default='medium',
        required=False,
    )
    qr_vertical_align = serializers.ChoiceField(
        choices=('top', 'center', 'bottom'),
        default='center',
        required=False,
    )
    qr_size_mm = serializers.FloatField(
        required=False,
        allow_null=True,
        default=None,
    )
    qr_bottom_offset_mm = serializers.FloatField(
        required=False,
        allow_null=True,
        default=None,
    )
    text_spacing = serializers.ChoiceField(
        choices=('tight', 'normal', 'loose'),
        default='normal',
        required=False,
    )
    uppercase_mode = serializers.ChoiceField(
        choices=('none', 'title', 'all'),
        default='none',
        required=False,
    )

    def validate_main_text(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError(
                'El texto principal no puede estar vacío.'
            )
        return value

    def validate_subtitle(self, value: str) -> str:
        return value.strip() if value else ''

    def validate_background_color(self, value: str) -> str:
        if not _HEX_RE.match(value):
            raise serializers.ValidationError(
                'El color de fondo debe ser un código hex válido (#RRGGBB).'
            )
        return value.upper()

    def validate_main_text_color(self, value: str) -> str | None:
        if not value:
            return None
        if not _HEX_RE.match(value):
            raise serializers.ValidationError(
                'main_text_color debe ser un código hex válido (#RRGGBB).'
            )
        return value.upper()

    def validate_subtitle_text_color(self, value: str) -> str | None:
        if not value:
            return None
        if not _HEX_RE.match(value):
            raise serializers.ValidationError(
                'subtitle_text_color debe ser un código hex válido (#RRGGBB).'
            )
        return value.upper()

    def validate_main_text_outline_color(self, value: str) -> str:
        if not value:
            return '#000000'
        if not _HEX_RE.match(value):
            raise serializers.ValidationError(
                'main_text_outline_color debe ser un código hex válido (#RRGGBB).'
            )
        return value.upper()

    def validate_subtitle_text_outline_color(self, value: str) -> str:
        if not value:
            return '#000000'
        if not _HEX_RE.match(value):
            raise serializers.ValidationError(
                'subtitle_text_outline_color debe ser un código hex válido (#RRGGBB).'
            )
        return value.upper()

    def validate_text_outline_width(self, value: float) -> float:
        rounded = round(value, 2)
        if rounded not in VALID_OUTLINE_WIDTHS:
            raise serializers.ValidationError(
                'text_outline_width debe ser uno de: 0.25, 0.4, 0.6, 0.8.'
            )
        return rounded

    def validate_qr_size_mm(self, value) -> float | None:
        if value is None:
            return None
        value = float(value)
        if not (22.0 <= value <= 90.0):
            raise serializers.ValidationError(
                'qr_size_mm debe estar entre 22 y 90 mm.'
            )
        return value

    def validate_qr_bottom_offset_mm(self, value) -> float | None:
        if value is None:
            return None
        value = float(value)
        if not (0.0 <= value <= 80.0):
            raise serializers.ValidationError(
                'qr_bottom_offset_mm debe estar entre 0 y 80 mm.'
            )
        return value
