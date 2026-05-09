"""
Generación de PDF para Carteles y Etiquetas.

Usa reportlab.canvas.Canvas (no Platypus) para control de grilla exacto.
Pagesize: A4 vertical.
Unidades: cm → pt via reportlab.lib.units.cm.
"""
from __future__ import annotations

import functools
import logging
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from .constants import CARD_GAP_CM, PAGE_MARGIN_CM
from .services import resolve_signage_logo

logger = logging.getLogger(__name__)

# ── Constantes de layout ─────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4           # 595.27 x 841.89 pt
PAGE_MARGIN    = PAGE_MARGIN_CM * cm
CARD_GAP       = CARD_GAP_CM * cm

# Configuración tipográfica
FONT_REGULAR   = 'Helvetica'
FONT_BOLD      = 'Helvetica-Bold'

# Máx caracteres antes de truncar
MAX_TITLE_CHARS = 40
MAX_DESC_CHARS  = 60
MAX_PROMO_CHARS = 20
MAX_PRICE_CHARS = 20

# Texto de encabezado predeterminado por template de promoción.
# Se usa cuando el item no trae promo_text.
_PROMO_DEFAULT_TEXTS: dict[str, str] = {
    'promo_offer':     'OFERTA',
    'promo_discount':  'DESCUENTO',
    'promo_2x1':       '2x1',
    'promo_combo':     'COMBO',
    'promo_clearance': 'LIQUIDACIÓN',
    'promo_weekly':    'PROMO SEMANAL',
}

# Ratios de alto de logo según tamaño configurado
_LOGO_SIZE_RATIOS: dict[str, float] = {
    'small':  0.10,
    'medium': 0.18,
    'large':  0.26,
    'xlarge': 0.36,
}

# Phase 6: tamaños de fuente absolutos (puntos) para cada nivel
_TITLE_FONT_SIZES: dict[str, float]     = {'small': 14, 'medium': 20, 'large': 28, 'xlarge': 36}
_PRICE_FONT_SIZES: dict[str, float]     = {'small': 16, 'medium': 24, 'large': 34, 'xlarge': 46}
_SECONDARY_FONT_SIZES: dict[str, float] = {'small': 10, 'medium': 14, 'large': 18, 'xlarge': 22}
# Phase 9: tamaños de fuente de título en promociones (más fuertes)
_PROMO_TITLE_FONT_SIZES: dict[str, float] = {'small': 16, 'medium': 22, 'large': 30, 'xlarge': 40}


# ── Utilidades ───────────────────────────────────────────────────────────────

def _truncate(text: str, max_chars: int) -> str:
    """Trunca el texto y añade ellipsis si supera max_chars."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1] + '…'


def _transform_text(value: str, text_transform: str) -> str:
    """Aplica transformación al texto (uppercase / none). No modifica precios."""
    if not value:
        return value
    if text_transform == 'uppercase':
        return value.upper()
    return value


def _fit_font_size(pdf: canvas.Canvas, text: str, max_width: float,
                   font: str, start_size: float, min_size: float = 5.0) -> float:
    """
    Reduce el tamaño de fuente hasta que el texto entre en max_width.
    Devuelve el tamaño de fuente resultante.
    """
    size = start_size
    while size >= min_size:
        pdf.setFont(font, size)
        if pdf.stringWidth(text, font, size) <= max_width:
            return size
        size -= 0.5
    return min_size


def _compute_grid(card_w: float, card_h: float):
    """
    Calcula cuántas columnas y filas caben en la página A4
    respetando márgenes y separación entre cards.

    Retorna (cols, rows) — mínimo 1×1.
    """
    usable_w = PAGE_W - 2 * PAGE_MARGIN
    usable_h = PAGE_H - 2 * PAGE_MARGIN
    cols = max(1, int((usable_w + CARD_GAP) / (card_w + CARD_GAP)))
    rows = max(1, int((usable_h + CARD_GAP) / (card_h + CARD_GAP)))
    return cols, rows


def _draw_logo(pdf: canvas.Canvas, logo_field, x: float, y_top: float,
               max_w: float, max_h: float) -> float:
    """
    Intenta dibujar el logo dentro del área (x, y_top - max_h) a (x + max_w, y_top).
    Devuelve la altura efectivamente usada (0.0 si falló o no hay logo).

    Compatible con FileSystemStorage (path local) y S3Boto3Storage (BytesIO).
    resolve_document_logo_path devuelve str, BytesIO o None; en todos los casos
    se construye un ImageReader que ReportLab acepta directamente en drawImage.
    """
    if logo_field is None:
        return 0.0
    try:
        from reportlab.lib.utils import ImageReader
        from apps.business.services import resolve_document_logo_path
        logo_src = resolve_document_logo_path(logo_field)
        if logo_src is None:
            logger.debug('_draw_logo: resolve_document_logo_path devolvió None, se omite logo')
            return 0.0
        reader = ImageReader(logo_src)
        img_w, img_h = reader.getSize()
        if img_w <= 0 or img_h <= 0:
            return 0.0
        scale = min(max_w / img_w, max_h / img_h, 1.0)
        draw_w = img_w * scale
        draw_h = img_h * scale
        # Centrar horizontalmente dentro de max_w
        x_offset = (max_w - draw_w) / 2
        pdf.drawImage(
            reader,
            x + x_offset,
            y_top - draw_h,
            width=draw_w,
            height=draw_h,
            preserveAspectRatio=True,
            mask='auto',
        )
        return draw_h
    except Exception:
        logger.warning('_draw_logo: no se pudo dibujar logo', exc_info=True)
        return 0.0


# ── Helpers de diseño (Phase 4) ──────────────────────────────────────────────

def _get_font_pair(font_preset: str) -> tuple[str, str]:
    """Devuelve (font_regular, font_bold) para el preset dado."""
    if font_preset == 'elegant':
        return 'Times-Roman', 'Times-Bold'
    if font_preset == 'condensed':
        return 'Courier', 'Courier-Bold'
    if font_preset == 'regular':
        return 'Helvetica', 'Helvetica'
    return 'Helvetica', 'Helvetica-Bold'   # 'bold' o default


def _resolve_font_size(size_key: str, base_pt: float) -> float:
    """
    Escala `base_pt` según el nivel enum del Phase 5.
    - 'small'  → base * 0.72
    - 'medium' → base * 1.0
    - 'large'  → base * 1.35
    - 'xlarge' → base * 1.75
    """
    multipliers = {'small': 0.72, 'medium': 1.0, 'large': 1.35, 'xlarge': 1.75}
    return base_pt * multipliers.get(size_key, 1.0)


def _resolve_border_color(border_style: str, border_color: str,
                           accent_color: str | None):
    """Devuelve un color ReportLab para el borde de diseño, o None si sin borde."""
    if border_style == 'none':
        return None
    if border_style == 'black':
        return colors.black
    if border_style == 'accent':
        try:
            return colors.HexColor(accent_color or '#1e293b')
        except Exception:
            return colors.black
    if border_style == 'custom':
        try:
            return colors.HexColor(border_color)
        except Exception:
            return colors.black
    return None


def _draw_design_border(
    pdf: canvas.Canvas,
    x: float, y_bottom: float, card_w: float, card_h: float,
    border_color_obj, border_width: int, border_radius: int,
    inner_padding: float = 0.0,
) -> None:
    """Dibuja el borde de diseño sólido, respetando inner_padding desde el borde exterior."""
    if border_color_obj is None:
        return
    line_w = max(0.3, border_width * 0.4)   # mapea 0..8 → 0..3.2 pt
    pdf.setStrokeColor(border_color_obj)
    pdf.setLineWidth(line_w)
    bx = x + inner_padding
    by = y_bottom + inner_padding
    bw = card_w - 2 * inner_padding
    bh = card_h - 2 * inner_padding
    if border_radius > 0:
        radius = border_radius * 0.08 * cm
        pdf.roundRect(bx, by, bw, bh, radius, stroke=1, fill=0)
    else:
        pdf.rect(bx, by, bw, bh, stroke=1, fill=0)


def _draw_card(pdf: canvas.Canvas, item: dict, x: float, y_bottom: float,
               card_w: float, card_h: float, logo_field,
               include_price: bool, show_cut_lines: bool,
               include_logo: bool, *, design: dict | None = None) -> None:
    """
    Dibuja un cartel de PRODUCTO en el canvas en la posición (x, y_bottom).

    Layout (Phase 6):
    1. Línea de corte exterior a la altura del card boundary.
    2. content_frame_padding_cm: espacio entre corte y marco del contenido.
    3. Logo arriba, FUERA del marco del contenido.
    4. Marco del contenido (solo alrededor del bloque textual).
    5. content_inner_padding_cm: padding dentro del marco.
    6. Texto centrado verticalmente en el área interior.
    """
    d              = design or {}
    font_preset    = d.get('font_preset', 'bold')
    layout_style   = d.get('layout_style', 'centered_product')
    logo_size      = d.get('logo_size', 'medium')
    accent_color   = d.get('accent_color')
    title_fsize    = d.get('title_font_size', 'medium')
    price_fsize    = d.get('price_font_size', 'large')
    sec_fsize      = d.get('secondary_font_size', 'small')

    # Phase 6: marco de contenido
    frame_enabled   = bool(d.get('content_frame_enabled', True))
    frame_color_hex = d.get('content_frame_color', '#000000')
    frame_width_val = int(d.get('content_frame_width', 2))
    frame_pad       = float(d.get('content_frame_padding_cm', 0.4)) * cm
    inner_pad       = float(d.get('content_inner_padding_cm', 0.3)) * cm
    # Phase 7: transformación de texto
    text_transform  = d.get('text_transform', 'none')
    # Phase 9: colores y espaciado
    header_text_color = d.get('header_text_color', '#DC2626')
    title_text_color  = d.get('title_text_color',  '#111827')
    price_text_color  = d.get('price_text_color',  '#000000')
    price_gap_pt      = float(d.get('price_gap_pt', 10))

    # framed_label siempre fuerza el marco
    if layout_style == 'framed_label':
        frame_enabled = True
    # minimal_label: sin marco, sin logo, padding mínimo
    if layout_style == 'minimal_label':
        frame_enabled = False
        frame_pad = 0.15 * cm

    font_reg, font_bold = _get_font_pair(font_preset)

    # ── 1. Línea de corte ────────────────────────────────────────────────────
    if show_cut_lines:
        pdf.setStrokeColor(colors.HexColor('#cccccc'))
        pdf.setLineWidth(0.25)
        pdf.setDash(3, 3)
        pdf.rect(x, y_bottom, card_w, card_h, stroke=1, fill=0)
        pdf.setDash()

    # ── 2. Área de contenido (dentro del frame_padding) ──────────────────────
    ca_x = x + frame_pad
    ca_y = y_bottom + frame_pad
    ca_w = card_w - 2 * frame_pad
    ca_h = card_h - 2 * frame_pad
    if ca_w <= 0 or ca_h <= 0:
        return

    # ── 3. Zona superior: logo / texto destacado / vacío ──────────────────────
    header_content_type = d.get('header_content_type', 'logo')
    header_text_cfg     = (d.get('header_text') or '').strip()
    logo_h_used = 0.0
    if layout_style != 'minimal_label':
        if header_content_type == 'logo':
            if include_logo and logo_field is not None:
                size_ratio = _LOGO_SIZE_RATIOS.get(logo_size, 0.18)
                logo_max_h = min(card_h * size_ratio, 1.5 * cm)
                logo_drawn = _draw_logo(
                    pdf, logo_field,
                    ca_x, ca_y + ca_h,
                    ca_w, logo_max_h,
                )
                if logo_drawn > 0:
                    logo_h_used = logo_drawn + 0.10 * cm
        elif header_content_type == 'highlight_text' and header_text_cfg:
            header_pt  = _TITLE_FONT_SIZES.get(title_fsize, 20)
            header_sz  = _fit_font_size(pdf, header_text_cfg, ca_w * 0.9, font_bold, header_pt, 6.0)
            text_y_pos = ca_y + ca_h - header_sz
            pdf.setFont(font_bold, header_sz)
            pdf.setFillColor(colors.HexColor(header_text_color))
            tw = pdf.stringWidth(header_text_cfg, font_bold, header_sz)
            pdf.drawString(ca_x + ca_w / 2 - tw / 2, text_y_pos, header_text_cfg)
            logo_h_used = header_sz + 0.12 * cm
        # header_content_type == 'none': logo_h_used stays 0.0

    # ── 4. Marco del contenido (solo alrededor del texto, debajo del logo) ───
    cf_x = ca_x
    cf_y = ca_y
    cf_w = ca_w
    cf_h = ca_h - logo_h_used

    if cf_h <= 0:
        return

    if frame_enabled and frame_width_val > 0:
        try:
            fc = colors.HexColor(frame_color_hex)
        except Exception:
            fc = colors.black
        lw = max(0.3, frame_width_val * 0.4)   # 0..8 → 0..3.2 pt
        pdf.setStrokeColor(fc)
        pdf.setLineWidth(lw)
        pdf.rect(cf_x, cf_y, cf_w, cf_h, stroke=1, fill=0)

    # ── 5. Área de texto (dentro del marco con inner_padding) ────────────────
    text_w   = cf_w - 2 * inner_pad
    text_h   = cf_h - 2 * inner_pad
    text_y   = cf_y + inner_pad
    center_x = cf_x + cf_w / 2

    if text_w <= 0 or text_h <= 0:
        return

    GAP = price_gap_pt  # pt separación entre elementos (Phase 9)

    title = _truncate(_transform_text((item.get('title') or '').strip(), text_transform), MAX_TITLE_CHARS)
    desc  = _truncate(_transform_text((item.get('description') or '').strip(), text_transform), MAX_DESC_CHARS)
    show_desc = layout_style in ('centered_product', 'framed_label')

    # Tamaños de fuente absolutos, se reducen automáticamente si no caben
    title_pt = _TITLE_FONT_SIZES.get(title_fsize, 20)
    price_pt = _PRICE_FONT_SIZES.get(price_fsize, 24)
    sec_pt   = _SECONDARY_FONT_SIZES.get(sec_fsize, 12)

    # price_focus: precio dominante, título pequeño
    if layout_style == 'price_focus':
        price_pt = _PRICE_FONT_SIZES.get(price_fsize, 24) * 1.5
        title_pt = _TITLE_FONT_SIZES.get(title_fsize, 20) * 0.7
        show_desc = False

    title_sz = _fit_font_size(pdf, title, text_w, font_bold, title_pt) if title else 0.0
    desc_sz  = _fit_font_size(pdf, desc, text_w, font_reg, sec_pt) if (desc and show_desc) else 0.0

    old_price_str = ''
    price_str     = ''
    old_price_sz  = 0.0
    price_sz      = 0.0
    if include_price:
        old_price_str = _truncate((item.get('old_price') or '').strip(), MAX_PRICE_CHARS)
        price_str     = _truncate((item.get('price') or '').strip(), MAX_PRICE_CHARS)
        if old_price_str:
            old_price_sz = _fit_font_size(pdf, f'$ {old_price_str}', text_w, font_reg, sec_pt)
        if price_str:
            price_sz = _fit_font_size(pdf, f'$ {price_str}', text_w, font_bold, price_pt)

    parts: list[tuple[str, float]] = []
    if title_sz:     parts.append(('title',     title_sz))
    if desc_sz:      parts.append(('desc',      desc_sz))
    if old_price_sz: parts.append(('old_price', old_price_sz))
    if price_sz:     parts.append(('price',     price_sz))

    block_h = sum(sz for _, sz in parts) + GAP * max(0, len(parts) - 1)

    # Centrado vertical
    if block_h <= text_h:
        start_y = text_y + (text_h + block_h) / 2
    else:
        start_y = text_y + text_h

    cursor_y = start_y

    # ── Dibujar elementos ─────────────────────────────────────────────────────
    for label, sz in parts:
        cursor_y -= sz
        if cursor_y < text_y:
            break

        if label == 'title':
            pdf.setFont(font_bold, sz)
            try:
                pdf.setFillColor(colors.HexColor(title_text_color))
            except Exception:
                pdf.setFillColor(colors.black)
            tw = pdf.stringWidth(title, font_bold, sz)
            pdf.drawString(center_x - tw / 2, cursor_y, title)

        elif label == 'desc':
            pdf.setFont(font_reg, sz)
            pdf.setFillColor(colors.HexColor('#64748b'))
            tw = pdf.stringWidth(desc, font_reg, sz)
            pdf.drawString(center_x - tw / 2, cursor_y, desc)

        elif label == 'old_price':
            text = f'$ {old_price_str}'
            pdf.setFont(font_reg, sz)
            pdf.setFillColor(colors.HexColor('#94a3b8'))
            tw = pdf.stringWidth(text, font_reg, sz)
            draw_x = center_x - tw / 2
            pdf.drawString(draw_x, cursor_y, text)
            strike_y = cursor_y + sz * 0.35
            pdf.setStrokeColor(colors.HexColor('#94a3b8'))
            pdf.setLineWidth(0.5)
            pdf.line(draw_x, strike_y, draw_x + tw, strike_y)

        elif label == 'price':
            text = f'$ {price_str}'
            pdf.setFont(font_bold, sz)
            if layout_style == 'price_focus':
                try:
                    pdf.setFillColor(colors.HexColor(accent_color or '#1e293b'))
                except Exception:
                    pdf.setFillColor(colors.black)
            else:
                try:
                    pdf.setFillColor(colors.HexColor(price_text_color))
                except Exception:
                    pdf.setFillColor(colors.black)
            tw = pdf.stringWidth(text, font_bold, sz)
            pdf.drawString(center_x - tw / 2, cursor_y, text)

        cursor_y -= GAP


def _draw_promotion_card(pdf: canvas.Canvas, item: dict, x: float, y_bottom: float,
                         card_w: float, card_h: float, logo_field,
                         include_price: bool, show_cut_lines: bool,
                         include_logo: bool, *,
                         template_code: str = 'promo_offer',
                         design: dict | None = None) -> None:
    """
    Dibuja un cartel de PROMOCIÓN.

    Layout (Phase 8):
    1. Línea de corte exterior.
    2. Padding exterior (frame_pad).
    3. Zona superior: logo / texto destacado / vacío (fuera del marco).
    4. Marco de contenido (debajo de zona superior).
    5. Texto centrado verticalmente dentro del marco.
    """
    d              = design or {}
    font_preset    = d.get('font_preset', 'bold')
    layout_style   = d.get('layout_style', 'centered_product')
    logo_size      = d.get('logo_size', 'medium')
    title_fsize    = d.get('title_font_size', 'medium')
    price_fsize    = d.get('price_font_size', 'large')
    sec_fsize      = d.get('secondary_font_size', 'small')

    # Phase 6: marco de contenido
    frame_enabled   = bool(d.get('content_frame_enabled', True))
    frame_color_hex = d.get('content_frame_color', '#000000')
    frame_width_val = int(d.get('content_frame_width', 2))
    frame_pad       = float(d.get('content_frame_padding_cm', 0.4)) * cm
    inner_pad       = float(d.get('content_inner_padding_cm', 0.3)) * cm
    # Phase 7: transformación de texto
    text_transform      = d.get('text_transform', 'none')
    # Phase 8: zona superior
    header_content_type = d.get('header_content_type', 'highlight_text')
    header_text_cfg     = (d.get('header_text') or '').strip()
    # Phase 9: colores y espaciado
    header_text_color = d.get('header_text_color', '#DC2626')
    title_text_color  = d.get('title_text_color',  '#111827')
    price_text_color  = d.get('price_text_color',  '#000000')
    price_gap_pt      = float(d.get('price_gap_pt', 10))

    if layout_style == 'framed_label':
        frame_enabled = True
    if layout_style == 'minimal_label':
        frame_enabled = False
        frame_pad = 0.15 * cm

    font_reg, font_bold = _get_font_pair(font_preset)

    # ── 1. Línea de corte ────────────────────────────────────────────────────
    if show_cut_lines:
        pdf.setStrokeColor(colors.HexColor('#cccccc'))
        pdf.setLineWidth(0.25)
        pdf.setDash(3, 3)
        pdf.rect(x, y_bottom, card_w, card_h, stroke=1, fill=0)
        pdf.setDash()

    # ── 2. Área de contenido (dentro del frame_padding) ──────────────────────
    ca_x = x + frame_pad
    ca_y = y_bottom + frame_pad
    ca_w = card_w - 2 * frame_pad
    ca_h = card_h - 2 * frame_pad
    if ca_w <= 0 or ca_h <= 0:
        return

    center_x = ca_x + ca_w / 2
    title_pt = _TITLE_FONT_SIZES.get(title_fsize, 20)
    price_pt = _PRICE_FONT_SIZES.get(price_fsize, 24)
    sec_pt   = _SECONDARY_FONT_SIZES.get(sec_fsize, 12)

    # ── 3. Zona superior (fuera del marco) ───────────────────────────────────
    header_h_used = 0.0
    if header_content_type == 'logo':
        if include_logo and logo_field is not None:
            size_ratio = _LOGO_SIZE_RATIOS.get(logo_size, 0.18)
            logo_max_h = min(card_h * size_ratio, 1.2 * cm)
            logo_drawn = _draw_logo(pdf, logo_field, ca_x, ca_y + ca_h, ca_w, logo_max_h)
            if logo_drawn > 0:
                header_h_used = logo_drawn + 0.10 * cm
    elif header_content_type == 'highlight_text':
        # texto: header_text_cfg > promo_text del item > default del template
        raw = (header_text_cfg
               or _transform_text((item.get('promo_text') or '').strip(), text_transform)
               or _PROMO_DEFAULT_TEXTS.get(template_code, ''))
        header_str = _truncate(raw, MAX_PROMO_CHARS)
        if header_str:
            header_pt     = _TITLE_FONT_SIZES.get(title_fsize, 20)
            header_sz     = _fit_font_size(pdf, header_str, ca_w * 0.9, font_bold, header_pt, 6.0)
            header_area_h = header_sz + 0.12 * cm
            text_y_pos    = ca_y + ca_h - header_sz
            if layout_style == 'promo_badge':
                badge_pad_x = 0.12 * cm
                badge_pad_y = 0.07 * cm
                tw      = pdf.stringWidth(header_str, font_bold, header_sz)
                badge_w = min(tw + badge_pad_x * 2, ca_w)
                badge_h = header_sz + badge_pad_y * 2
                badge_x = center_x - badge_w / 2
                badge_y = text_y_pos - badge_pad_y
                pdf.setFillColor(colors.HexColor('#dc2626'))
                pdf.roundRect(badge_x, badge_y, badge_w, badge_h, 2, stroke=0, fill=1)
                pdf.setFont(font_bold, header_sz)
                pdf.setFillColor(colors.white)
                pdf.drawString(center_x - tw / 2, text_y_pos, header_str)
                header_area_h = header_sz + badge_pad_y * 2 + 0.12 * cm
            else:
                pdf.setFont(font_bold, header_sz)
                try:
                    pdf.setFillColor(colors.HexColor(header_text_color))
                except Exception:
                    pdf.setFillColor(colors.HexColor('#DC2626'))
                tw = pdf.stringWidth(header_str, font_bold, header_sz)
                pdf.drawString(center_x - tw / 2, text_y_pos, header_str)
            header_h_used = header_area_h
    # header_content_type == 'none': header_h_used stays 0.0

    # ── 4. Marco del contenido (debajo de zona superior) ─────────────────────
    cf_x = ca_x
    cf_y = ca_y
    cf_w = ca_w
    cf_h = ca_h - header_h_used

    if cf_h <= 0:
        return

    if frame_enabled and frame_width_val > 0:
        try:
            fc = colors.HexColor(frame_color_hex)
        except Exception:
            fc = colors.black
        lw = max(0.3, frame_width_val * 0.4)
        pdf.setStrokeColor(fc)
        pdf.setLineWidth(lw)
        pdf.rect(cf_x, cf_y, cf_w, cf_h, stroke=1, fill=0)

    # ── 5. Texto centrado verticalmente dentro del marco ─────────────────────
    text_w   = cf_w - 2 * inner_pad
    text_h   = cf_h - 2 * inner_pad
    text_y   = cf_y + inner_pad
    center_x = cf_x + cf_w / 2

    if text_w <= 0 or text_h <= 0:
        return

    GAP = price_gap_pt  # pt separación entre elementos (Phase 9)

    # promo_text va dentro del marco solo si el header NO lo usa ya
    promo_in_frame = header_content_type != 'highlight_text'
    promo_str = ''
    promo_sz  = 0.0
    if promo_in_frame:
        promo_raw = _transform_text((item.get('promo_text') or '').strip(), text_transform)
        if not promo_raw:
            promo_raw = _PROMO_DEFAULT_TEXTS.get(template_code, '')
        promo_str = _truncate(promo_raw, MAX_PROMO_CHARS)
        if promo_str:
            promo_sz = _fit_font_size(pdf, promo_str, text_w * 0.9, font_bold, title_pt, 6.0)

    title = _truncate(_transform_text((item.get('title') or '').strip(), text_transform), MAX_TITLE_CHARS)
    desc  = _truncate(_transform_text((item.get('description') or '').strip(), text_transform), MAX_DESC_CHARS)
    show_desc = layout_style not in ('minimal_label', 'framed_label')

    # Phase 9: usar tabla de tamaños de título promocional (más grandes)
    promo_title_pt = _PROMO_TITLE_FONT_SIZES.get(title_fsize, 22)
    title_sz = _fit_font_size(pdf, title, text_w, font_bold, promo_title_pt, 5.0) if title else 0.0
    desc_sz  = _fit_font_size(pdf, desc, text_w, font_reg, sec_pt, 5.0) if (desc and show_desc) else 0.0

    old_price_str = ''
    price_str     = ''
    old_price_sz  = 0.0
    price_sz      = 0.0
    if include_price:
        old_price_str = _truncate((item.get('old_price') or '').strip(), MAX_PRICE_CHARS)
        price_str     = _truncate((item.get('price') or '').strip(), MAX_PRICE_CHARS)
        if old_price_str:
            old_price_sz = _fit_font_size(pdf, f'$ {old_price_str}', text_w, font_reg, sec_pt, 5.0)
        if price_str:
            price_sz = _fit_font_size(pdf, f'$ {price_str}', text_w, font_bold, price_pt, 5.0)

    parts: list[tuple[str, float]] = []
    if promo_sz:     parts.append(('promo',     promo_sz))
    if title_sz:     parts.append(('title',     title_sz))
    if desc_sz:      parts.append(('desc',      desc_sz))
    if old_price_sz: parts.append(('old_price', old_price_sz))
    if price_sz:     parts.append(('price',     price_sz))

    block_h = sum(sz for _, sz in parts) + GAP * max(0, len(parts) - 1)

    # Centrado vertical
    if block_h <= text_h:
        start_y = text_y + (text_h + block_h) / 2
    else:
        start_y = text_y + text_h

    cursor_y = start_y

    # ── Dibujar elementos ─────────────────────────────────────────────────────
    for label, sz in parts:
        cursor_y -= sz
        if cursor_y < text_y:
            break

        if label == 'promo':
            if layout_style == 'promo_badge':
                badge_pad_x = 0.12 * cm
                badge_pad_y = 0.07 * cm
                tw      = pdf.stringWidth(promo_str, font_bold, sz)
                badge_w = min(tw + badge_pad_x * 2, text_w)
                badge_h = sz + badge_pad_y * 2
                badge_x = center_x - badge_w / 2
                badge_y = cursor_y - badge_pad_y
                pdf.setFillColor(colors.HexColor('#dc2626'))
                pdf.roundRect(badge_x, badge_y, badge_w, badge_h, 2, stroke=0, fill=1)
                pdf.setFont(font_bold, sz)
                pdf.setFillColor(colors.white)
                tw = pdf.stringWidth(promo_str, font_bold, sz)
                pdf.drawString(center_x - tw / 2, cursor_y, promo_str)
            else:
                pdf.setFont(font_bold, sz)
                try:
                    pdf.setFillColor(colors.HexColor(header_text_color))
                except Exception:
                    pdf.setFillColor(colors.HexColor('#DC2626'))
                tw = pdf.stringWidth(promo_str, font_bold, sz)
                pdf.drawString(center_x - tw / 2, cursor_y, promo_str)

        elif label == 'title':
            pdf.setFont(font_bold, sz)
            try:
                pdf.setFillColor(colors.HexColor(title_text_color))
            except Exception:
                pdf.setFillColor(colors.black)
            tw = pdf.stringWidth(title, font_bold, sz)
            pdf.drawString(center_x - tw / 2, cursor_y, title)

        elif label == 'desc':
            pdf.setFont(font_reg, sz)
            pdf.setFillColor(colors.HexColor('#64748b'))
            tw = pdf.stringWidth(desc, font_reg, sz)
            pdf.drawString(center_x - tw / 2, cursor_y, desc)

        elif label == 'old_price':
            text = f'$ {old_price_str}'
            pdf.setFont(font_reg, sz)
            pdf.setFillColor(colors.HexColor('#94a3b8'))
            tw = pdf.stringWidth(text, font_reg, sz)
            draw_x = center_x - tw / 2
            pdf.drawString(draw_x, cursor_y, text)
            strike_y = cursor_y + sz * 0.35
            pdf.setStrokeColor(colors.HexColor('#94a3b8'))
            pdf.setLineWidth(0.5)
            pdf.line(draw_x, strike_y, draw_x + tw, strike_y)

        elif label == 'price':
            text = f'$ {price_str}'
            pdf.setFont(font_bold, sz)
            try:
                pdf.setFillColor(colors.HexColor(price_text_color))
            except Exception:
                pdf.setFillColor(colors.black)
            tw = pdf.stringWidth(text, font_bold, sz)
            pdf.drawString(center_x - tw / 2, cursor_y, text)

        cursor_y -= GAP


# ── Función principal ────────────────────────────────────────────────────────

def render_signage_pdf(data: dict[str, Any], business=None) -> bytes:
    """
    Genera el PDF de Carteles y Etiquetas a partir de los datos validados
    por GeneratePDFSerializer.

    Args:
        data:     validated_data del serializer
        business: instancia de Business (para logo); puede ser None

    Returns:
        Bytes del PDF generado.
    """
    card_size      = data['card_size']
    card_w         = card_size['width_cm'] * cm
    card_h         = card_size['height_cm'] * cm
    logo_variant   = data.get('logo_variant', 'none')
    include_logo   = data.get('include_logo', False)
    include_price  = data.get('include_price', True)
    show_cut_lines = data.get('show_cut_lines', True)

    # Opciones de diseño visual (Phase 4 + 5 + 6) — todos opcionales con defaults
    design: dict = {
        'layout_style':  data.get('layout_style', 'centered_product'),
        'font_preset':   data.get('font_preset', 'bold'),
        # Phase 4 (backward compat, no se usa en layout nuevo)
        'border_style':  data.get('border_style', 'none'),
        'border_color':  data.get('border_color', '#000000'),
        'border_width':  int(data.get('border_width', 2)),
        'border_radius': int(data.get('border_radius', 0)),
        'logo_size':     data.get('logo_size', 'medium'),
        'logo_position': data.get('logo_position', 'top_center'),
        'accent_color':  None,
        # Phase 5 (tipografía)
        'title_font_size':     data.get('title_font_size', 'medium'),
        'price_font_size':     data.get('price_font_size', 'large'),
        'secondary_font_size': data.get('secondary_font_size', 'small'),
        # Phase 6: marco de contenido
        'content_frame_enabled':    bool(data.get('content_frame_enabled', True)),
        'content_frame_color':      data.get('content_frame_color', '#000000'),
        'content_frame_width':      int(data.get('content_frame_width', 2)),
        'content_frame_padding_cm': float(data.get('content_frame_padding_cm', 0.4)),
        'content_inner_padding_cm': float(data.get('content_inner_padding_cm', 0.3)),
        # Phase 7: transformación de texto
        'text_transform': data.get('text_transform', 'none'),
        # Phase 8: zona superior
        'header_content_type': (
            data.get('header_content_type')
            or ('highlight_text' if data.get('type') == 'promotion' else 'logo')
        ),
        'header_text': data.get('header_text') or '',
        # Phase 9: colores y espaciado
        'header_text_color': data.get('header_text_color', '#DC2626'),
        'title_text_color':  data.get('title_text_color',  '#111827'),
        'price_text_color':  data.get('price_text_color',  '#000000'),
        'price_gap_pt':      float(data.get('price_gap_pt', 10)),
    }

    # Expandir items por copies
    expanded_items: list[dict] = []
    for item in data['items']:
        copies = item.get('copies', 1)
        for _ in range(copies):
            expanded_items.append(item)

    # Resolver logo una sola vez
    logo_field = None
    if include_logo and business is not None and logo_variant != 'none':
        logo_field = resolve_signage_logo(business, logo_variant)

    # Calcular grilla
    cols, rows = _compute_grid(card_w, card_h)
    cards_per_page = cols * rows

    # Elegir función de dibujo según template
    template_code = data.get('template_code', 'product_price_simple')
    if template_code == 'product_price_simple':
        draw_fn = _draw_card
    else:
        draw_fn = functools.partial(_draw_promotion_card, template_code=template_code)

    # Crear PDF
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle('Carteles y Etiquetas')

    for idx, item in enumerate(expanded_items):
        card_idx = idx % cards_per_page

        # Nueva página al comenzar
        if card_idx == 0 and idx > 0:
            pdf.showPage()

        col = card_idx % cols
        row = card_idx // cols

        # Coordenadas del card (bottom-left en ReportLab)
        x_card = PAGE_MARGIN + col * (card_w + CARD_GAP)
        y_card = PAGE_H - PAGE_MARGIN - (row + 1) * card_h - row * CARD_GAP

        draw_fn(
            pdf, item,
            x=x_card,
            y_bottom=y_card,
            card_w=card_w,
            card_h=card_h,
            logo_field=logo_field,
            include_price=include_price,
            show_cut_lines=show_cut_lines,
            include_logo=include_logo,
            design=design,
        )

    pdf.save()
    return buffer.getvalue()

