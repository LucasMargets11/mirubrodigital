"""
Servicio de generación de PDF para Carteles QR de Reseñas PRO.

Tres templates diferenciados:

  simple_centered — logo + texto + QR en layout vertical centrado.
                    Ideal para a4_portrait, a5_portrait, sticker_square, desk_card.

  qr_left         — QR a la izquierda, texto a la derecha (dos columnas).
                    Ideal para a4_landscape, half_a4, desk_card.
                    Fallback automático a simple_centered si el formato es
                    cuadrado o portrait (aspect_ratio < QR_LEFT_MIN_ASPECT).

  bold_cta        — Fondo intenso, texto grande, QR dentro de caja blanca.
                    Diseño promocional. Contraste automático según luminancia.

El QR siempre apunta a /r/{slug}/, nunca directamente a Google.
No se agregan dependencias nuevas — segno y ReportLab ya están en el proyecto.
"""
from __future__ import annotations

import io
import logging
import pathlib

import segno
from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

# ── Tamaños de página (width, height) en puntos ReportLab ─────────────────────
POSTER_PAGE_SIZES: dict[str, tuple[float, float]] = {
    'a4_portrait':    (21.0 * cm, 29.7 * cm),
    'a4_landscape':   (29.7 * cm, 21.0 * cm),
    'a5_portrait':    (14.8 * cm, 21.0 * cm),
    'half_a4':        (21.0 * cm, 14.85 * cm),
    'desk_card':      (15.0 * cm, 10.0 * cm),
    'sticker_square': (10.0 * cm, 10.0 * cm),
}

# ── Constantes de layout ──────────────────────────────────────────────────────
MARGIN            = 1.0 * cm    # margen uniforme en todos los bordes
MIN_QR_SIZE       = 22.0 * mm   # tamaño mínimo del QR escaneable (~22 mm)
MAX_MAIN_PT       = 28.0        # texto principal — simple_centered / qr_left
MAX_MAIN_BOLD_PT  = 36.0        # texto principal — bold_cta (más grande)
MAX_SUB_PT        = 16.0        # subtítulo — simple_centered / qr_left
MAX_SUB_BOLD_PT   = 18.0        # subtítulo — bold_cta
MIN_FONT_PT       = 6.0         # tamaño mínimo de fuente (pt)
QR_BOX_PADDING    = 0.4 * cm    # padding interior de la caja blanca (bold_cta)

# Nuevos defaults para los campos de posición/tamaño del QR
QR_DEFAULT_SIZE_MM          = 48.0   # tamaño default cuando no se especifica qr_size_mm
QR_DEFAULT_BOTTOM_OFFSET_MM = 16.0   # offset inferior default en mm
QR_DEFAULT_VERTICAL_ALIGN   = 'center'

# qr_left: ratio mínimo ancho/alto para usar el layout de dos columnas.
# Por debajo de este valor (portrait o cuadrado) se hace fallback a simple_centered.
QR_LEFT_MIN_ASPECT = 1.2

FONT_BOLD = 'Helvetica-Bold'
FONT_REG  = 'Helvetica'

# Mapa de codes de tipografía (title_font) a fuentes builtin de ReportLab
FONT_MAP: dict[str, str] = {
    'sans_bold':  'Helvetica-Bold',
    'serif_bold': 'Times-Bold',
    'mono_bold':  'Courier-Bold',
}

# ── Sistema de tipografías Premium (font_family + font_weight) ────────────────
# Directorio con los TTF estáticos generados desde Google Fonts.
# qr_posters.py  →  apps/reviews/  →  apps/  →  src/  →  assets/fonts/posters/
POSTER_FONTS_DIR = pathlib.Path(__file__).parent.parent.parent / 'assets' / 'fonts' / 'posters'

# Registro de familias disponibles.  Sólo se incluyen los pesos para los que
# existe un archivo TTF real en POSTER_FONTS_DIR.
POSTER_FONT_REGISTRY: dict[str, dict] = {
    'cinzel': {
        'weights': {
            'regular': ('Cinzel-Regular', 'Cinzel-Regular.ttf'),
            'bold':    ('Cinzel-Bold',    'Cinzel-Bold.ttf'),
            'black':   ('Cinzel-Black',   'Cinzel-Black.ttf'),
        },
    },
    'montserrat': {
        'weights': {
            'regular': ('Montserrat-Regular', 'Montserrat-Regular.ttf'),
            'bold':    ('Montserrat-Bold',    'Montserrat-Bold.ttf'),
            'black':   ('Montserrat-Black',   'Montserrat-Black.ttf'),
        },
    },
    'poppins': {
        'weights': {
            'regular': ('Poppins-Regular', 'Poppins-Regular.ttf'),
            'bold':    ('Poppins-Bold',    'Poppins-Bold.ttf'),
            'black':   ('Poppins-Black',   'Poppins-Black.ttf'),
        },
    },
    'raleway': {
        'weights': {
            'regular': ('Raleway-Regular', 'Raleway-Regular.ttf'),
            'bold':    ('Raleway-Bold',    'Raleway-Bold.ttf'),
            'black':   ('Raleway-Black',   'Raleway-Black.ttf'),
        },
    },
    'playfair_display': {
        'weights': {
            'regular': ('PlayfairDisplay-Regular', 'PlayfairDisplay-Regular.ttf'),
            'bold':    ('PlayfairDisplay-Bold',    'PlayfairDisplay-Bold.ttf'),
            'black':   ('PlayfairDisplay-Black',   'PlayfairDisplay-Black.ttf'),
        },
    },
    'work_sans': {
        'weights': {
            'regular': ('WorkSans-Regular', 'WorkSans-Regular.ttf'),
            'bold':    ('WorkSans-Bold',    'WorkSans-Bold.ttf'),
            'black':   ('WorkSans-Black',   'WorkSans-Black.ttf'),
        },
    },
    'lato': {
        'weights': {
            'regular': ('Lato-Regular', 'Lato-Regular.ttf'),
            'bold':    ('Lato-Bold',    'Lato-Bold.ttf'),
            'black':   ('Lato-Black',   'Lato-Black.ttf'),
        },
    },
    'oswald': {
        'weights': {
            'regular': ('Oswald-Regular', 'Oswald-Regular.ttf'),
            'bold':    ('Oswald-Bold',    'Oswald-Bold.ttf'),
            # No tiene Black
        },
    },
    'cormorant_garamond': {
        'weights': {
            'regular': ('CormorantGaramond-Regular', 'CormorantGaramond-Regular.ttf'),
            'bold':    ('CormorantGaramond-Bold',    'CormorantGaramond-Bold.ttf'),
            # No tiene Black
        },
    },
    'libre_baskerville': {
        'weights': {
            'regular': ('LibreBaskerville-Regular', 'LibreBaskerville-Regular.ttf'),
            'bold':    ('LibreBaskerville-Bold',    'LibreBaskerville-Bold.ttf'),
            # No tiene Black
        },
    },
}

# Cache para evitar registrar la misma fuente múltiples veces.
_POSTER_FONT_REGISTERED: set[str] = set()


def resolve_poster_font(font_family: str | None, font_weight: str | None) -> str:
    """
    Resuelve y registra (si es necesario) un TTF de Google Fonts para ReportLab.

    Retorna el nombre ReportLab (str) que se puede pasar a ``canvas.setFont()``.
    Si la familia o el peso no están disponibles, normaliza automáticamente:
      - Peso desconocido → intenta 'bold', luego el primer peso disponible.
      - Familia desconocida → retorna FONT_BOLD (Helvetica-Bold) sin lanzar.
    """
    if not font_family:
        return FONT_BOLD

    family_entry = POSTER_FONT_REGISTRY.get(font_family)
    if family_entry is None:
        logger.warning("resolve_poster_font: familia desconocida %r, usando Helvetica-Bold", font_family)
        return FONT_BOLD

    available_weights = family_entry['weights']

    # Normalizar el peso: si no existe, bajar a bold; si tampoco, tomar el primero.
    weight_key = font_weight or 'bold'
    if weight_key not in available_weights:
        if 'bold' in available_weights:
            weight_key = 'bold'
        else:
            weight_key = next(iter(available_weights))

    reportlab_name, filename = available_weights[weight_key]

    # Registrar el TTF si aún no lo hemos hecho en esta sesión.
    if reportlab_name not in _POSTER_FONT_REGISTERED:
        ttf_path = POSTER_FONTS_DIR / filename
        if not ttf_path.exists():
            logger.warning(
                "resolve_poster_font: TTF no encontrado en %s, usando Helvetica-Bold",
                ttf_path,
            )
            return FONT_BOLD
        try:
            pdfmetrics.registerFont(TTFont(reportlab_name, str(ttf_path)))
            _POSTER_FONT_REGISTERED.add(reportlab_name)
        except Exception:
            logger.exception(
                "resolve_poster_font: error registrando %s desde %s", reportlab_name, ttf_path,
            )
            return FONT_BOLD

    return reportlab_name

# Multiplicadores de tamaño del QR por qr_scale (legacy — mantenido por backward compat)
QR_SCALE_MAP: dict[str, float] = {
    'small':  0.85,
    'medium': 1.0,
    'large':  1.15,
}

# Mapa de qr_scale legacy a mm reales (usado para backward compat cuando qr_size_mm=None)
QR_SCALE_TO_MM: dict[str, float] = {
    'small':  32.0,
    'medium': 48.0,
    'large':  68.0,
}

# Separación entre título y subtítulo por text_spacing
TEXT_SPACING_MAP: dict[str, float] = {
    'tight':  0.1 * cm,
    'normal': 0.25 * cm,
    'loose':  0.45 * cm,
}


# ── Helpers internos ──────────────────────────────────────────────────────────

def _build_review_landing_url(slug: str) -> str:
    """
    Construye la URL pública de la landing de reseñas.
    Replica la lógica de _build_review_landing_url en reviews/views.py
    para evitar import circular (views.py importa este módulo).
    """
    base_url = (
        getattr(settings, 'PUBLIC_MENU_BASE_URL', None)
        or getattr(settings, 'FRONTEND_URL', None)
        or 'http://localhost:3000'
    )
    return f"{base_url.rstrip('/')}/r/{slug}/"


def _generate_qr_png(url: str) -> bytes:
    """
    Genera el QR como PNG en memoria via segno.
    scale=10 + border=1 produce un QR limpio embebible en PDF.
    No se usa build_qr_svg() de common/qr.py porque esa función devuelve
    un data URI SVG para uso en HTML, no un PNG binario.
    """
    qr = segno.make(url, micro=False)
    buf = io.BytesIO()
    qr.save(buf, kind='png', scale=10, border=1)
    return buf.getvalue()


def _resolve_qr_size_pt(qr_size_mm: float | None, qr_scale_key: str) -> float:
    """
    Resuelve el tamaño del QR en puntos ReportLab.

    Si qr_size_mm está definido, lo convierte directamente a puntos.
    Si no, usa el mapa legacy qr_scale → mm para backward compat.
    El resultado se clampea a MIN_QR_SIZE como piso de escaneo seguro.
    """
    if qr_size_mm is not None:
        resolved_mm = max(22.0, min(90.0, float(qr_size_mm)))
    else:
        resolved_mm = QR_SCALE_TO_MM.get(qr_scale_key, QR_DEFAULT_SIZE_MM)
    return max(resolved_mm * mm, MIN_QR_SIZE)


def _fit_font(pdf: canvas.Canvas, text: str, max_width: float,
              font: str, max_pt: float) -> float:
    """Reduce el tamaño de fuente hasta que el texto entre en max_width."""
    size = max_pt
    while size > MIN_FONT_PT:
        if pdf.stringWidth(text, font, size) <= max_width:
            return size
        size -= 0.5
    return MIN_FONT_PT


def _is_dark(hex_color: str) -> bool:
    """True si la luminancia relativa del color es < 0.5."""
    try:
        h = hex_color.lstrip('#')
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5
    except Exception:
        return False


def _text_colors(background_color: str) -> tuple[colors.Color, colors.Color]:
    """Devuelve (color_principal, color_subtítulo) con contraste sobre el fondo."""
    dark = _is_dark(background_color)
    main = colors.white if dark else colors.HexColor('#111827')
    sub  = colors.HexColor('#D1D5DB') if dark else colors.HexColor('#64748B')
    return main, sub


def _resolve_text_colors(
    effective_bg_color: str,
    main_text_color: str | None,
    subtitle_text_color: str | None,
) -> tuple[colors.Color, colors.Color]:
    """
    Combina contraste automático con overrides opcionales del usuario.
    Si el usuario envió un color, se respeta aunque el contraste sea bajo.
    """
    auto_main, auto_sub = _text_colors(effective_bg_color)
    resolved_main = colors.HexColor(main_text_color) if main_text_color else auto_main
    resolved_sub  = colors.HexColor(subtitle_text_color) if subtitle_text_color else auto_sub
    return resolved_main, resolved_sub


def _draw_text_with_optional_outline(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    font_name: str,
    font_size: float,
    fill_color: colors.Color,
    outline_enabled: bool = False,
    outline_color: colors.Color | None = None,
    outline_width: float = 0.4,
) -> None:
    """
    Dibuja texto con borde/contorno opcional.

    Cuando outline_enabled=True usa PDF text render mode 2 (fill+stroke)
    mediante un textObject de ReportLab — sin duplicar paths manualmente.

    saveState/restoreState garantizan que los cambios de color, linewidth
    y textRenderMode no afecten al resto del dibujo.
    """
    pdf.saveState()
    pdf.setFont(font_name, font_size)
    pdf.setFillColor(fill_color)
    if outline_enabled and outline_color is not None:
        pdf.setStrokeColor(outline_color)
        pdf.setLineWidth(outline_width)
        t = pdf.beginText(x, y)
        t.setTextRenderMode(2)  # PDF mode 2: fill + stroke
        t.textOut(text)
        pdf.drawText(t)
    else:
        pdf.drawString(x, y, text)
    pdf.restoreState()


def _try_draw_logo(
    pdf: canvas.Canvas,
    business,
    include_logo: bool,
    logo_variant: str,
    x: float,
    y_top: float,
    max_w: float,
    max_h: float,
) -> float:
    """
    Intenta dibujar el logo. Devuelve la altura usada (0.0 si se omite o falla).
    Nunca lanza excepciones — errors se loguean como warning.
    """
    if not include_logo or logo_variant == 'none':
        return 0.0
    try:
        from apps.printables.pdf import _draw_logo                 # noqa: PLC0415
        from apps.printables.services import resolve_signage_logo  # noqa: PLC0415
        logo_field = resolve_signage_logo(business, logo_variant)
        if logo_field is None:
            return 0.0
        return _draw_logo(pdf, logo_field, x, y_top, max_w, max_h)
    except Exception:
        logger.warning(
            '_try_draw_logo: no se pudo dibujar logo (business=%s)',
            getattr(business, 'pk', '?'),
            exc_info=True,
        )
        return 0.0


def _draw_logo_at_position(
    pdf: canvas.Canvas,
    business,
    include_logo: bool,
    logo_variant: str,
    logo_position: str,
    logo_margin_pt: float,
    page_w: float,
    page_h: float,
    max_logo_h: float,
) -> float:
    """
    Dibuja el logo en la posición indicada dentro del área de la página.
    Devuelve la altura usada (0.0 si se omitió o falló).
    Nunca lanza excepciones.

    Coordenadas ReportLab: y=0 abajo, y=page_h arriba.
    logo_position: top-left | top-center | top-right |
                   bottom-left | bottom-center | bottom-right |
                   middle-left | middle-right
    """
    if not include_logo or logo_variant == 'none':
        return 0.0
    try:
        from apps.printables.pdf import _draw_logo                 # noqa: PLC0415
        from apps.printables.services import resolve_signage_logo  # noqa: PLC0415
        logo_field = resolve_signage_logo(business, logo_variant)
        if logo_field is None:
            return 0.0

        max_logo_w = page_w * 0.45  # máximo 45% del ancho de la página

        m = logo_margin_pt
        pos = logo_position or 'top-center'

        # Calcular x de origen del área del logo
        if 'left' in pos:
            x = m
        elif 'right' in pos:
            x = page_w - m - max_logo_w
        else:  # center
            x = (page_w - max_logo_w) / 2

        # Calcular y_top (en ReportLab, y_top = parte superior del logo)
        if 'top' in pos:
            y_top = page_h - m
        elif 'bottom' in pos:
            y_top = m + max_logo_h
        else:  # middle
            y_top = page_h / 2 + max_logo_h / 2

        # Clampear para no salirnos de la página
        x = max(m, min(x, page_w - m - max_logo_w))
        y_top = max(max_logo_h, min(y_top, page_h - m))

        return _draw_logo(pdf, logo_field, x, y_top, max_logo_w, max_logo_h)
    except Exception:
        logger.warning(
            '_draw_logo_at_position: no se pudo dibujar logo (business=%s)',
            getattr(business, 'pk', '?'),
            exc_info=True,
        )
        return 0.0


def _draw_qr(
    pdf: canvas.Canvas,
    qr_png: bytes,
    x: float,
    y: float,
    size: float,
) -> None:
    """Dibuja el PNG del QR en (x, y) con el tamaño cuadrado dado."""
    from reportlab.lib.utils import ImageReader  # noqa: PLC0415
    pdf.drawImage(
        ImageReader(io.BytesIO(qr_png)),
        x, y,
        width=size,
        height=size,
        preserveAspectRatio=True,
        mask='auto',
    )


def _draw_background_image_cover(
    pdf: canvas.Canvas,
    image_bytes: bytes,
    page_w: float,
    page_h: float,
) -> None:
    """
    Dibuja image_bytes como fondo en modo cover:
    escala hasta cubrir toda la página manteniendo proporción,
    recorta el sobrante mediante clipPath.

    Calidad de impresión: usa los bytes originales sin compresión adicional.
    Recomendación futura: validar resolución mínima de 300 DPI para impresión
    profesional (actualmente no se bloquea por resolución baja).
    """
    from reportlab.lib.utils import ImageReader  # noqa: PLC0415
    reader = ImageReader(io.BytesIO(image_bytes))
    img_w_px, img_h_px = reader.getSize()

    # Escala cover: la mayor de las dos escalas necesarias para cubrir la página
    scale = max(page_w / img_w_px, page_h / img_h_px)
    draw_w = img_w_px * scale
    draw_h = img_h_px * scale

    # Centrar (el exceso queda fuera del clipPath)
    x = (page_w - draw_w) / 2
    y = (page_h - draw_h) / 2

    pdf.saveState()
    clip = pdf.beginPath()
    clip.rect(0, 0, page_w, page_h)
    pdf.clipPath(clip, stroke=0, fill=0)
    pdf.drawImage(
        reader, x, y,
        width=draw_w, height=draw_h,
        preserveAspectRatio=False,
        mask=None,   # imagen de fondo debe ser siempre opaca (no respetar alpha de PNG)
    )
    pdf.restoreState()


def _draw_dark_overlay(
    pdf: canvas.Canvas,
    page_w: float,
    page_h: float,
    opacity: float = 0.45,
) -> None:
    """Overlay oscuro semitransparente para mejorar legibilidad sobre imagen de fondo."""
    pdf.saveState()
    pdf.setFillAlpha(opacity)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.rect(0, 0, page_w, page_h, stroke=0, fill=1)
    pdf.restoreState()


def _draw_qr_in_white_box(
    pdf: canvas.Canvas,
    qr_png: bytes,
    cx: float,
    y_bottom: float,
    qr_size: float,
    padding: float,
) -> None:
    """
    Dibuja una caja blanca redondeada y el QR centrado dentro de ella.
    cx es el centro horizontal. y_bottom es la base de la caja.
    """
    box_size = qr_size + 2 * padding
    box_x = cx - box_size / 2
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(colors.HexColor('#E5E7EB'))
    pdf.roundRect(box_x, y_bottom, box_size, box_size,
                  radius=0.3 * cm, stroke=1, fill=1)
    _draw_qr(pdf, qr_png, cx - qr_size / 2, y_bottom + padding, qr_size)


# ── Layouts ───────────────────────────────────────────────────────────────────

def _render_simple_centered(
    pdf: canvas.Canvas,
    page_w: float,
    page_h: float,
    main_text: str,
    subtitle: str,
    bg_color: str,
    qr_png: bytes,
    business,
    include_logo: bool,
    logo_variant: str,
    force_qr_box: bool = False,
    title_font_rl: str = FONT_BOLD,
    txt_color=None,
    sub_color=None,
    main_outline_enabled: bool = False,
    main_outline_color: colors.Color | None = None,
    sub_outline_enabled: bool = False,
    sub_outline_color: colors.Color | None = None,
    outline_width: float = 0.4,
    qr_scale: float = 1.0,
    text_spacing_gap: float = 0.25 * cm,
    qr_size_pt: float | None = None,
    qr_vertical_align: str = 'center',
    qr_bottom_offset_pt: float = 16.0 * mm,
    logo_position: str = 'top-center',
    logo_margin_pt: float = 8.0 * mm,
) -> None:
    """
    Layout vertical centrado:
      logo (opcional, posición configurable) → main_text → subtitle → QR.

    qr_size_pt: tamaño del QR en puntos. Si None, se usa qr_scale para calcularlo.
    qr_vertical_align: 'top' | 'center' | 'bottom'
    qr_bottom_offset_pt: desplazamiento desde el borde inferior (solo para 'bottom').
    logo_position: posición absoluta del logo (ver VALID_LOGO_POSITIONS).
    logo_margin_pt: margen desde el borde de la página en puntos.
    """
    usable_w = page_w - 2 * MARGIN
    if txt_color is None or sub_color is None:
        _auto_main, _auto_sub = _text_colors(bg_color)
        if txt_color is None:
            txt_color = _auto_main
        if sub_color is None:
            sub_color = _auto_sub
    cursor_y = page_h - MARGIN

    # Logo — se dibuja en posición absoluta; si es top-*, descuenta espacio del cursor
    max_logo_h = min(page_h * 0.12, 2.0 * cm)
    logo_h = _draw_logo_at_position(
        pdf, business, include_logo, logo_variant,
        logo_position, logo_margin_pt, page_w, page_h, max_logo_h,
    )
    # Solo descontar espacio del cursor si el logo está arriba
    if logo_h > 0 and (logo_position or 'top-center').startswith('top'):
        cursor_y -= logo_h + 0.25 * cm

    cursor_y -= 0.4 * cm

    # Texto principal
    main_sz = _fit_font(pdf, main_text, usable_w, title_font_rl, MAX_MAIN_PT)
    cursor_y -= main_sz
    tw = pdf.stringWidth(main_text, title_font_rl, main_sz)
    _draw_text_with_optional_outline(
        pdf, main_text, MARGIN + (usable_w - tw) / 2, cursor_y,
        title_font_rl, main_sz, txt_color,
        outline_enabled=main_outline_enabled, outline_color=main_outline_color,
        outline_width=outline_width,
    )

    # Subítulo
    if subtitle:
        cursor_y -= text_spacing_gap
        sub_sz = _fit_font(pdf, subtitle, usable_w, title_font_rl, MAX_SUB_PT)
        cursor_y -= sub_sz
        tw_sub = pdf.stringWidth(subtitle, title_font_rl, sub_sz)
        _draw_text_with_optional_outline(
            pdf, subtitle, MARGIN + (usable_w - tw_sub) / 2, cursor_y,
            title_font_rl, sub_sz, sub_color,
            outline_enabled=sub_outline_enabled, outline_color=sub_outline_color,
            outline_width=outline_width,
        )

    cursor_y -= 0.5 * cm

    # QR — tamaño y posición vertical
    qr_area_h = cursor_y - MARGIN
    if qr_area_h < MIN_QR_SIZE:
        logger.warning(
            '_render_simple_centered: espacio insuficiente para QR '
            '(qr_area_h=%.1f pt < %.1f pt)',
            qr_area_h, MIN_QR_SIZE,
        )
        return

    # Resolver tamaño del QR
    if qr_size_pt is not None:
        qr_size = max(min(qr_size_pt, usable_w), MIN_QR_SIZE)
    else:
        qr_size = max(min(min(usable_w, qr_area_h) * qr_scale, usable_w), MIN_QR_SIZE)

    qr_x = MARGIN + (usable_w - qr_size) / 2

    # Resolver posición vertical
    if qr_vertical_align == 'bottom':
        qr_y = MARGIN + qr_bottom_offset_pt
    elif qr_vertical_align == 'top':
        # Justo debajo del texto (cursor_y ya bajó después del texto + gap)
        qr_y = max(MARGIN, cursor_y - qr_size)
    else:
        # 'center': centrado en el área disponible bajo el texto
        qr_y = MARGIN + (qr_area_h - qr_size) / 2

    # Clampear para no salirnos de los márgenes
    qr_y = max(MARGIN, min(qr_y, cursor_y - qr_size if cursor_y > qr_size else MARGIN))

    if force_qr_box:
        inner = max(qr_size - 2 * QR_BOX_PADDING, MIN_QR_SIZE)
        _draw_qr_in_white_box(pdf, qr_png, page_w / 2, qr_y, inner, QR_BOX_PADDING)
    else:
        _draw_qr(pdf, qr_png, qr_x, qr_y, qr_size)


def _render_qr_left(
    pdf: canvas.Canvas,
    page_w: float,
    page_h: float,
    main_text: str,
    subtitle: str,
    bg_color: str,
    qr_png: bytes,
    business,
    include_logo: bool,
    logo_variant: str,
    force_qr_box: bool = False,
    title_font_rl: str = FONT_BOLD,
    txt_color=None,
    sub_color=None,
    main_outline_enabled: bool = False,
    main_outline_color: colors.Color | None = None,
    sub_outline_enabled: bool = False,
    sub_outline_color: colors.Color | None = None,
    outline_width: float = 0.4,
    qr_scale: float = 1.0,
    text_spacing_gap: float = 0.25 * cm,
    qr_size_pt: float | None = None,
    qr_vertical_align: str = 'center',
    qr_bottom_offset_pt: float = 16.0 * mm,
    logo_position: str = 'top-center',
    logo_margin_pt: float = 8.0 * mm,
) -> None:
    """
    Layout de dos columnas: QR a la izquierda, texto a la derecha.

    Usa el formato horizontal para maximizar el espacio del QR en paisaje.
    Fallback automático a simple_centered si page_w/page_h < QR_LEFT_MIN_ASPECT
    (formatos portrait o cuadrados: a4_portrait, a5_portrait, sticker_square).
    """
    if page_w / page_h < QR_LEFT_MIN_ASPECT:
        _render_simple_centered(
            pdf, page_w, page_h, main_text, subtitle, bg_color,
            qr_png, business, include_logo, logo_variant, force_qr_box,
            title_font_rl=title_font_rl, txt_color=txt_color, sub_color=sub_color,
            main_outline_enabled=main_outline_enabled, main_outline_color=main_outline_color,
            sub_outline_enabled=sub_outline_enabled, sub_outline_color=sub_outline_color,
            outline_width=outline_width,
            qr_scale=qr_scale, text_spacing_gap=text_spacing_gap,
            qr_size_pt=qr_size_pt, qr_vertical_align=qr_vertical_align,
            qr_bottom_offset_pt=qr_bottom_offset_pt,
            logo_position=logo_position, logo_margin_pt=logo_margin_pt,
        )
        return

    usable_w = page_w - 2 * MARGIN
    usable_h = page_h - 2 * MARGIN
    if txt_color is None or sub_color is None:
        _auto_main, _auto_sub = _text_colors(bg_color)
        if txt_color is None:
            txt_color = _auto_main
        if sub_color is None:
            sub_color = _auto_sub

    # División de columnas: 45% izquierda (QR), 55% derecha (texto)
    COL_GAP     = 0.4 * cm
    left_col_w  = usable_w * 0.45 - COL_GAP / 2
    right_col_w = usable_w * 0.55 - COL_GAP / 2
    right_col_x = MARGIN + left_col_w + COL_GAP

    # ── Columna izquierda: QR ─────────────────────────────────────────────────
    if qr_size_pt is not None:
        qr_size = max(min(qr_size_pt, left_col_w), MIN_QR_SIZE)
    else:
        qr_size = max(min(min(left_col_w, usable_h) * qr_scale, left_col_w), MIN_QR_SIZE)
    qr_x = MARGIN + (left_col_w - qr_size) / 2

    # Vertical align dentro de la columna izquierda
    if qr_vertical_align == 'bottom':
        qr_y = MARGIN + qr_bottom_offset_pt
    elif qr_vertical_align == 'top':
        qr_y = MARGIN + usable_h - qr_size
    else:
        qr_y = MARGIN + (usable_h - qr_size) / 2

    qr_y = max(MARGIN, min(qr_y, MARGIN + usable_h - qr_size))

    if force_qr_box:
        cx_left = MARGIN + left_col_w / 2
        inner = max(qr_size - 2 * QR_BOX_PADDING, MIN_QR_SIZE)
        _draw_qr_in_white_box(pdf, qr_png, cx_left, qr_y, inner, QR_BOX_PADDING)
    else:
        _draw_qr(pdf, qr_png, qr_x, qr_y, qr_size)

    # ── Columna derecha: logo (posición configurable) + bloque de texto centrado ─
    cursor_y = MARGIN + usable_h  # = page_h - MARGIN

    max_logo_h = min(usable_h * 0.18, 1.8 * cm)
    logo_h = _draw_logo_at_position(
        pdf, business, include_logo, logo_variant,
        logo_position, logo_margin_pt, page_w, page_h, max_logo_h,
    )
    # Solo descontar cursor si logo está arriba (en la columna de texto)
    if logo_h > 0 and (logo_position or 'top-center').startswith('top'):
        cursor_y -= logo_h + 0.4 * cm

    # Pre-calcular bloque de texto para centrarlo verticalmente en el espacio restante
    main_sz = _fit_font(pdf, main_text, right_col_w, title_font_rl, MAX_MAIN_PT)
    sub_sz  = _fit_font(pdf, subtitle, right_col_w, title_font_rl, MAX_SUB_PT) if subtitle else 0.0
    block_h = main_sz + (text_spacing_gap + sub_sz if subtitle else 0.0)

    remaining     = cursor_y - MARGIN
    # top del bloque de texto (cursor desciende en ReportLab desde la parte superior)
    block_top     = MARGIN + (remaining + block_h) / 2

    # Texto principal
    _draw_text_with_optional_outline(
        pdf, main_text, right_col_x, block_top - main_sz,
        title_font_rl, main_sz, txt_color,
        outline_enabled=main_outline_enabled, outline_color=main_outline_color,
        outline_width=outline_width,
    )

    # Subítulo
    if subtitle:
        sub_y = block_top - main_sz - text_spacing_gap - sub_sz
        _draw_text_with_optional_outline(
            pdf, subtitle, right_col_x, sub_y,
            title_font_rl, sub_sz, sub_color,
            outline_enabled=sub_outline_enabled, outline_color=sub_outline_color,
            outline_width=outline_width,
        )


def _render_bold_cta(
    pdf: canvas.Canvas,
    page_w: float,
    page_h: float,
    main_text: str,
    subtitle: str,
    bg_color: str,
    qr_png: bytes,
    business,
    include_logo: bool,
    logo_variant: str,
    title_font_rl: str = FONT_BOLD,
    txt_color=None,
    sub_color=None,
    main_outline_enabled: bool = False,
    main_outline_color: colors.Color | None = None,
    sub_outline_enabled: bool = False,
    sub_outline_color: colors.Color | None = None,
    outline_width: float = 0.4,
    qr_scale: float = 1.0,
    text_spacing_gap: float = 0.25 * cm,
    qr_size_pt: float | None = None,
    qr_vertical_align: str = 'center',
    qr_bottom_offset_pt: float = 16.0 * mm,
    logo_position: str = 'top-center',
    logo_margin_pt: float = 8.0 * mm,
) -> None:
    """
    Layout promocional:
      logo (pequeño, arriba) → texto principal grande → subtítulo → QR en caja blanca.

    El QR siempre tiene fondo blanco para garantizar contraste,
    independientemente del color de fondo del cartel.
    El texto adapta su color automáticamente según la luminancia del fondo.
    """
    usable_w = page_w - 2 * MARGIN
    if txt_color is None or sub_color is None:
        _auto_main, _auto_sub = _text_colors(bg_color)
        if txt_color is None:
            txt_color = _auto_main
        if sub_color is None:
            sub_color = _auto_sub
    cursor_y = page_h - MARGIN

    # Logo — posición configurable; solo descuenta cursor si está arriba
    max_logo_h = min(page_h * 0.10, 1.8 * cm)
    logo_h = _draw_logo_at_position(
        pdf, business, include_logo, logo_variant,
        logo_position, logo_margin_pt, page_w, page_h, max_logo_h,
    )
    if logo_h > 0 and (logo_position or 'top-center').startswith('top'):
        cursor_y -= logo_h + 0.3 * cm

    cursor_y -= 0.3 * cm

    # Texto principal (fuente más grande para impacto visual)
    main_sz = _fit_font(pdf, main_text, usable_w, title_font_rl, MAX_MAIN_BOLD_PT)
    cursor_y -= main_sz
    tw = pdf.stringWidth(main_text, title_font_rl, main_sz)
    _draw_text_with_optional_outline(
        pdf, main_text, MARGIN + (usable_w - tw) / 2, cursor_y,
        title_font_rl, main_sz, txt_color,
        outline_enabled=main_outline_enabled, outline_color=main_outline_color,
        outline_width=outline_width,
    )

    # Subítulo
    if subtitle:
        cursor_y -= text_spacing_gap
        sub_sz = _fit_font(pdf, subtitle, usable_w, title_font_rl, MAX_SUB_BOLD_PT)
        cursor_y -= sub_sz
        tw_sub = pdf.stringWidth(subtitle, title_font_rl, sub_sz)
        _draw_text_with_optional_outline(
            pdf, subtitle, MARGIN + (usable_w - tw_sub) / 2, cursor_y,
            title_font_rl, sub_sz, sub_color,
            outline_enabled=sub_outline_enabled, outline_color=sub_outline_color,
            outline_width=outline_width,
        )

    cursor_y -= 0.6 * cm

    # QR con caja blanca para garantizar legibilidad
    qr_area_h = cursor_y - MARGIN
    if qr_area_h < MIN_QR_SIZE:
        logger.warning(
            '_render_bold_cta: espacio insuficiente para QR '
            '(qr_area_h=%.1f pt < %.1f pt)',
            qr_area_h, MIN_QR_SIZE,
        )
        return

    # Resolver tamaño del QR
    max_box = min(usable_w, qr_area_h)
    if qr_size_pt is not None:
        qr_size = max(min(qr_size_pt, usable_w - 2 * QR_BOX_PADDING), MIN_QR_SIZE)
    else:
        qr_size = max(min((max_box - 2 * QR_BOX_PADDING) * qr_scale, usable_w - 2 * QR_BOX_PADDING), MIN_QR_SIZE)

    cx = page_w / 2

    # Resolver posición vertical
    if qr_vertical_align == 'bottom':
        box_y = MARGIN + qr_bottom_offset_pt
    elif qr_vertical_align == 'top':
        box_y = max(MARGIN, cursor_y - qr_size)
    else:
        box_y = max(MARGIN, MARGIN + (qr_area_h - qr_size) / 2)

    box_y = max(MARGIN, box_y)

    if qr_size >= MIN_QR_SIZE:
        _draw_qr_in_white_box(pdf, qr_png, cx, box_y, qr_size, QR_BOX_PADDING)
    else:
        _draw_qr(pdf, qr_png, cx - qr_size / 2, box_y, qr_size)


# ── Función pública ───────────────────────────────────────────────────────────

def render_qr_poster_pdf(
    data: dict,
    business,
    background_image_bytes: bytes | None = None,
) -> bytes:
    """
    Genera el PDF del cartel QR de Reseñas PRO.

    Despacha al layout correspondiente según template_code:
      - simple_centered: layout vertical centrado (todos los tamaños)
      - qr_left:         dos columnas horizontal (landscape; fallback a centrado en portrait)
      - bold_cta:        diseño promocional con QR en caja blanca

    Args:
        data:                   dict validado por GenerateQrPosterSerializer
        business:               instancia de Business (debe tener .slug)
        background_image_bytes: bytes de la imagen de fondo (JPG/PNG) o None

    Returns:
        bytes del PDF generado (comienza con %PDF)
    """
    poster_size      = data['poster_size']
    template_code    = data['template_code']
    main_text        = data['main_text']
    subtitle         = data.get('subtitle') or ''
    include_logo     = data.get('include_logo', True)
    logo_variant     = data.get('logo_variant', 'default')
    logo_position    = data.get('logo_position', 'top-center')
    logo_margin_pt   = float(data.get('logo_margin_mm', 8.0)) * mm
    background_color     = data.get('background_color', '#FFFFFF')
    background_mode      = data.get('background_mode', 'color')
    title_font              = data.get('title_font', 'sans_bold')
    main_text_color         = data.get('main_text_color') or None
    subtitle_text_color     = data.get('subtitle_text_color') or None
    main_outline_enabled    = data.get('main_text_outline_enabled', False)
    main_outline_color_hex  = data.get('main_text_outline_color') or '#000000'
    sub_outline_enabled     = data.get('subtitle_text_outline_enabled', False)
    sub_outline_color_hex   = data.get('subtitle_text_outline_color') or '#000000'
    outline_width           = data.get('text_outline_width', 0.4)
    qr_scale_key            = data.get('qr_scale', 'medium')
    text_spacing_key        = data.get('text_spacing', 'normal')
    uppercase_mode          = data.get('uppercase_mode', 'none')

    # Nuevos parámetros de personalización del QR
    qr_size_mm_raw          = data.get('qr_size_mm') or None
    qr_vertical_align       = data.get('qr_vertical_align', QR_DEFAULT_VERTICAL_ALIGN)
    qr_bottom_offset_mm_raw = data.get('qr_bottom_offset_mm')
    if qr_bottom_offset_mm_raw is None:
        qr_bottom_offset_mm_raw = QR_DEFAULT_BOTTOM_OFFSET_MM

    # Resolver tamaño del QR en puntos (nuevo sistema mm-based)
    qr_size_pt = _resolve_qr_size_pt(qr_size_mm_raw, qr_scale_key)
    qr_bottom_offset_pt = float(qr_bottom_offset_mm_raw) * mm

    # Aplicar mayúsculas antes de renderizar
    if uppercase_mode == 'title':
        main_text = main_text.upper()
    elif uppercase_mode == 'all':
        main_text = main_text.upper()
        subtitle  = subtitle.upper()

    qr_scale_factor   = QR_SCALE_MAP.get(qr_scale_key, 1.0)
    text_spacing_gap  = TEXT_SPACING_MAP.get(text_spacing_key, 0.25 * cm)

    page_w, page_h = POSTER_PAGE_SIZES[poster_size]

    # URL pública de la landing — siempre /r/{slug}/, nunca Google directo
    slug        = getattr(business, 'slug', None) or ''
    landing_url = _build_review_landing_url(slug)

    # ── Canvas ────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=(page_w, page_h))

    # ── Fondo ─────────────────────────────────────────────────────────────────
    try:
        bg_color_obj = colors.HexColor(background_color)
    except Exception:
        bg_color_obj = colors.white
        background_color = '#FFFFFF'

    if background_mode == 'image' and background_image_bytes:
        # Imagen de fondo en modo cover + overlay oscuro para legibilidad
        _draw_background_image_cover(pdf, background_image_bytes, page_w, page_h)
        _draw_dark_overlay(pdf, page_w, page_h)
        # Después del overlay oscuro, los textos deben ser blancos
        effective_bg_color = '#000000'
    else:
        pdf.setFillColor(bg_color_obj)
        pdf.rect(0, 0, page_w, page_h, stroke=0, fill=1)
        effective_bg_color = background_color

    # El QR necesita caja blanca cuando el fondo efectivo es oscuro
    force_qr_box = _is_dark(effective_bg_color)

    # Tipografía del título y colores de texto (con fallback automático de contraste)
    font_family_key  = data.get('font_family') or None
    font_weight_key  = data.get('font_weight') or None
    if font_family_key:
        title_font_rl = resolve_poster_font(font_family_key, font_weight_key)
    else:
        title_font_rl = FONT_MAP.get(title_font, FONT_BOLD)
    txt_color, sub_color = _resolve_text_colors(
        effective_bg_color, main_text_color, subtitle_text_color,
    )
    main_outline_color = colors.HexColor(main_outline_color_hex)
    sub_outline_color  = colors.HexColor(sub_outline_color_hex)

    # ── QR PNG (generado una vez, compartido por todos los layouts) ───────────
    qr_png = _generate_qr_png(landing_url)

    # ── Despacho al layout ────────────────────────────────────────────────────
    if template_code == 'qr_left':
        _render_qr_left(
            pdf, page_w, page_h, main_text, subtitle, effective_bg_color,
            qr_png, business, include_logo, logo_variant, force_qr_box,
            title_font_rl=title_font_rl, txt_color=txt_color, sub_color=sub_color,
            main_outline_enabled=main_outline_enabled, main_outline_color=main_outline_color,
            sub_outline_enabled=sub_outline_enabled, sub_outline_color=sub_outline_color,
            outline_width=outline_width,
            qr_scale=qr_scale_factor, text_spacing_gap=text_spacing_gap,
            qr_size_pt=qr_size_pt, qr_vertical_align=qr_vertical_align,
            qr_bottom_offset_pt=qr_bottom_offset_pt,
            logo_position=logo_position, logo_margin_pt=logo_margin_pt,
        )
    elif template_code == 'bold_cta':
        # bold_cta siempre usa caja blanca para el QR — no necesita force_qr_box
        _render_bold_cta(
            pdf, page_w, page_h, main_text, subtitle, effective_bg_color,
            qr_png, business, include_logo, logo_variant,
            title_font_rl=title_font_rl, txt_color=txt_color, sub_color=sub_color,
            main_outline_enabled=main_outline_enabled, main_outline_color=main_outline_color,
            sub_outline_enabled=sub_outline_enabled, sub_outline_color=sub_outline_color,
            outline_width=outline_width,
            qr_scale=qr_scale_factor, text_spacing_gap=text_spacing_gap,
            qr_size_pt=qr_size_pt, qr_vertical_align=qr_vertical_align,
            qr_bottom_offset_pt=qr_bottom_offset_pt,
            logo_position=logo_position, logo_margin_pt=logo_margin_pt,
        )
    else:
        # 'simple_centered' y cualquier template futuro aún no diferenciado
        _render_simple_centered(
            pdf, page_w, page_h, main_text, subtitle, effective_bg_color,
            qr_png, business, include_logo, logo_variant, force_qr_box,
            title_font_rl=title_font_rl, txt_color=txt_color, sub_color=sub_color,
            main_outline_enabled=main_outline_enabled, main_outline_color=main_outline_color,
            sub_outline_enabled=sub_outline_enabled, sub_outline_color=sub_outline_color,
            outline_width=outline_width,
            qr_scale=qr_scale_factor, text_spacing_gap=text_spacing_gap,
            qr_size_pt=qr_size_pt, qr_vertical_align=qr_vertical_align,
            qr_bottom_offset_pt=qr_bottom_offset_pt,
            logo_position=logo_position, logo_margin_pt=logo_margin_pt,
        )

    pdf.showPage()
    pdf.save()
    return buf.getvalue()
