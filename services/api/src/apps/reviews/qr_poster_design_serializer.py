"""
Serializer para los endpoints de historial de diseños QR de Reseñas PRO.

GET/POST  /api/v1/reviews/qr-posters/designs/
GET/PATCH/DELETE /api/v1/reviews/qr-posters/designs/<uuid:id>/
"""
from __future__ import annotations

import re

from rest_framework import serializers

from .models import ReviewQrPosterDesign
from .qr_poster_serializer import (
    VALID_BACKGROUND_MODES,
    VALID_FONT_FAMILIES,
    VALID_FONT_WEIGHTS,
    VALID_LOGO_POSITIONS,
    VALID_LOGO_VARIANTS,
    VALID_OUTLINE_WIDTHS,
    VALID_POSTER_SIZES,
    VALID_TEMPLATE_CODES,
    VALID_TITLE_FONTS,
    _HEX_RE,
)

# ── Payload sub-serializer ─────────────────────────────────────────────────────
# Reuses the same validation rules as GenerateQrPosterSerializer so the stored
# payload is guaranteed to be renderable by render_qr_poster_pdf().


class PosterPayloadSerializer(serializers.Serializer):
    """Validates the JSON configuration stored inside ReviewQrPosterDesign.payload."""

    poster_size = serializers.ChoiceField(choices=VALID_POSTER_SIZES)
    template_code = serializers.ChoiceField(choices=VALID_TEMPLATE_CODES)
    main_text = serializers.CharField(max_length=80, allow_blank=False)
    subtitle = serializers.CharField(max_length=80, allow_blank=True, required=False, default='')
    include_logo = serializers.BooleanField(default=True)
    logo_variant = serializers.ChoiceField(choices=VALID_LOGO_VARIANTS, default='default')
    logo_position = serializers.ChoiceField(choices=VALID_LOGO_POSITIONS, default='top-center', required=False)
    logo_margin_mm = serializers.FloatField(default=8.0, required=False, min_value=0.0, max_value=40.0)
    background_color = serializers.CharField(default='#FFFFFF', required=False)
    background_mode = serializers.ChoiceField(choices=VALID_BACKGROUND_MODES, default='color')
    title_font = serializers.ChoiceField(choices=VALID_TITLE_FONTS, default='sans_bold', required=False)
    font_family = serializers.ChoiceField(
        choices=VALID_FONT_FAMILIES, default=None, required=False, allow_null=True,
    )
    font_weight = serializers.ChoiceField(
        choices=VALID_FONT_WEIGHTS, default=None, required=False, allow_null=True,
    )
    main_text_color = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    subtitle_text_color = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    main_text_outline_enabled = serializers.BooleanField(default=False, required=False)
    main_text_outline_color = serializers.CharField(required=False, allow_null=True, allow_blank=True, default='#000000')
    subtitle_text_outline_enabled = serializers.BooleanField(default=False, required=False)
    subtitle_text_outline_color = serializers.CharField(required=False, allow_null=True, allow_blank=True, default='#000000')
    text_outline_width = serializers.FloatField(default=0.4, required=False)
    qr_scale = serializers.ChoiceField(choices=('small', 'medium', 'large'), default='medium', required=False)
    qr_vertical_align = serializers.ChoiceField(
        choices=('top', 'center', 'bottom'), default='center', required=False,
    )
    qr_size_mm = serializers.FloatField(required=False, allow_null=True, default=None)
    qr_bottom_offset_mm = serializers.FloatField(required=False, allow_null=True, default=None)
    text_spacing = serializers.ChoiceField(choices=('tight', 'normal', 'loose'), default='normal', required=False)
    uppercase_mode = serializers.ChoiceField(choices=('none', 'title', 'all'), default='none', required=False)

    def validate_main_text(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError('El texto principal no puede estar vacío.')
        return value

    def validate_subtitle(self, value: str) -> str:
        return value.strip() if value else ''

    def validate_background_color(self, value: str) -> str:
        if not _HEX_RE.match(value):
            raise serializers.ValidationError('El color de fondo debe ser un código hex válido (#RRGGBB).')
        return value.upper()

    def _validate_optional_hex(self, value: str, field: str) -> str | None:
        if not value:
            return None
        if not _HEX_RE.match(value):
            raise serializers.ValidationError(f'{field} debe ser un código hex válido (#RRGGBB).')
        return value.upper()

    def validate_main_text_color(self, value: str) -> str | None:
        return self._validate_optional_hex(value, 'main_text_color')

    def validate_subtitle_text_color(self, value: str) -> str | None:
        return self._validate_optional_hex(value, 'subtitle_text_color')

    def validate_main_text_outline_color(self, value: str) -> str:
        if not value:
            return '#000000'
        if not _HEX_RE.match(value):
            raise serializers.ValidationError('main_text_outline_color debe ser un código hex válido (#RRGGBB).')
        return value.upper()

    def validate_subtitle_text_outline_color(self, value: str) -> str:
        if not value:
            return '#000000'
        if not _HEX_RE.match(value):
            raise serializers.ValidationError('subtitle_text_outline_color debe ser un código hex válido (#RRGGBB).')
        return value.upper()

    def validate_text_outline_width(self, value: float) -> float:
        if value not in VALID_OUTLINE_WIDTHS:
            raise serializers.ValidationError(
                f'text_outline_width debe ser uno de: {list(VALID_OUTLINE_WIDTHS)}.'
            )
        return value

    def validate_qr_size_mm(self, value) -> float | None:
        if value is None:
            return None
        value = float(value)
        if not (22.0 <= value <= 90.0):
            raise serializers.ValidationError('qr_size_mm debe estar entre 22 y 90 mm.')
        return value

    def validate_qr_bottom_offset_mm(self, value) -> float | None:
        if value is None:
            return None
        value = float(value)
        if not (0.0 <= value <= 80.0):
            raise serializers.ValidationError('qr_bottom_offset_mm debe estar entre 0 y 80 mm.')
        return value


# ── Main serializer ────────────────────────────────────────────────────────────

class QrPosterDesignSerializer(serializers.ModelSerializer):
    """
    Read/write serializer for ReviewQrPosterDesign.

    - `payload` is validated via PosterPayloadSerializer.
    - `background_image` is a URL on read (SerializerMethodField) and
      handled separately via request.FILES on write — it is NOT part of
      the JSON body to avoid mixing file and JSON in a single field.
    - `background_image_url` exposes the storage URL to the frontend.
    """

    payload = serializers.JSONField()
    background_image_url = serializers.SerializerMethodField()

    class Meta:
        model = ReviewQrPosterDesign
        fields = [
            'id',
            'name',
            'payload',
            'background_image_url',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'background_image_url']

    def get_background_image_url(self, obj) -> str | None:
        if not obj.background_image:
            return None
        try:
            url = obj.background_image.url
        except Exception:
            return None
        # Mirror the pattern used by MenuCategorySerializer / MenuItemSerializer:
        # if the URL is relative (local FileSystemStorage), make it absolute using
        # the incoming request so the frontend receives a usable URL in both
        # local dev and S3 environments.
        request = self.context.get('request')
        if request and url.startswith('/'):
            return request.build_absolute_uri(url)
        return url

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError('El nombre no puede estar vacío.')
        return value

    def validate_payload(self, value: dict) -> dict:
        sub = PosterPayloadSerializer(data=value)
        if not sub.is_valid():
            raise serializers.ValidationError(sub.errors)
        return sub.validated_data
