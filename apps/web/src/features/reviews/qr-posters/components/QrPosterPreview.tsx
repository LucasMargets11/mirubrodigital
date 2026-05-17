'use client';

import { useEffect, useState } from 'react';

import {
    POSTER_SIZES,
    QR_BOTTOM_OFFSET_MM_DEFAULT,
    resolveQrSizeMm,
    getPosterFontFamily,
    resolvePosterFontWeight,
    LOGO_MARGIN_MM_DEFAULT,
} from '../constants';
import type { GenerateQrPosterPayload } from '../types';
import { useBusinessBrandingQuery } from '@/features/business/branding/hooks';

interface Props {
    payload: GenerateQrPosterPayload;
    /** URL de imagen de fondo guardada en el servidor (cargada desde diseño). */
    savedBgUrl?: string | null;
}

/** Devuelve true si el color hex tiene baja luminancia (texto blanco necesario). */
function isColorDark(hex: string): boolean {
    try {
        const h = hex.replace('#', '');
        const r = parseInt(h.slice(0, 2), 16);
        const g = parseInt(h.slice(2, 4), 16);
        const b = parseInt(h.slice(4, 6), 16);
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5;
    } catch {
        return false;
    }
}

/**
 * Convierte una URL relativa devuelta por el backend (p.ej. /media/...) en
 * una URL absoluta usando NEXT_PUBLIC_API_URL como origen.
 * Las URLs absolutas (http/https/blob/data) se devuelven sin cambios.
 * Defensa extra en caso de que el serializer no reciba request context.
 */
function resolveMediaUrl(url: string | null | undefined): string | null {
    if (!url) return null;
    if (
        url.startsWith('http://') ||
        url.startsWith('https://') ||
        url.startsWith('blob:') ||
        url.startsWith('data:')
    ) {
        return url;
    }
    if (url.startsWith('/')) {
        const apiOrigin = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
        return `${apiOrigin}${url}`;
    }
    return url;
}

/**
 * Preview CSS aproximada del cartel — no es pixel-perfect respecto al PDF,
 * pero refleja tamaño proporcional, color, template, texto y placeholder QR.
 */

// ── Sub-components (declared at module level to avoid react-hooks/static-components) ──

interface QrBlockProps {
    style: React.CSSProperties;
    qrBoxPadding: number;
    useQrWhiteBox: boolean;
    qrBoxBorderRadius: number;
    qrSizePx: number;
    dark: boolean;
}

function QrBlock({ style, qrBoxPadding, useQrWhiteBox, qrBoxBorderRadius, qrSizePx, dark }: QrBlockProps) {
    return (
        <div
            style={{
                position: 'absolute',
                padding: qrBoxPadding,
                backgroundColor: useQrWhiteBox ? '#FFFFFF' : 'transparent',
                boxShadow: useQrWhiteBox ? '0 1px 6px rgba(0,0,0,0.18)' : 'none',
                borderRadius: qrBoxBorderRadius,
                ...style,
            }}
        >
            <QrPlaceholderIcon size={qrSizePx} dark={useQrWhiteBox ? false : dark} />
        </div>
    );
}

interface LogoContentProps {
    resolvedLogoUrl: string | null;
    logoMaxW: number;
    logoMaxH: number;
    placeholderBg: string;
}

function LogoContent({ resolvedLogoUrl, logoMaxW, logoMaxH, placeholderBg }: LogoContentProps) {
    if (resolvedLogoUrl) {
        return (
            // eslint-disable-next-line @next/next/no-img-element
            <img
                src={resolvedLogoUrl}
                alt="Logo"
                style={{ maxWidth: logoMaxW, maxHeight: logoMaxH, objectFit: 'contain', display: 'block' }}
                onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
            />
        );
    }
    return (
        <div
            className="rounded-sm"
            style={{ width: logoMaxW * 0.75, height: logoMaxH * 0.5, backgroundColor: placeholderBg }}
        />
    );
}

export function QrPosterPreview({ payload, savedBgUrl }: Props) {
    const {
        poster_size, template_code, main_text, subtitle, background_color, include_logo,
        logo_variant, logo_position, logo_margin_mm,
        background_mode, background_image, title_font, font_family, font_weight,
        main_text_color, subtitle_text_color,
        main_text_outline_enabled, main_text_outline_color,
        subtitle_text_outline_enabled, subtitle_text_outline_color,
        text_outline_width,
        qr_scale, text_spacing, uppercase_mode,
        qr_vertical_align, qr_bottom_offset_mm,
    } = payload;

    const sizeInfo = POSTER_SIZES.find((s) => s.code === poster_size);
    const aspectRatio = sizeInfo?.aspectRatio ?? 21 / 29.7;

    // Object URL for image background preview — created and revoked via useEffect
    const [imageUrl, setImageUrl] = useState<string | null>(null);
    useEffect(() => {
        if (background_mode === 'image' && background_image instanceof File) {
            const url = URL.createObjectURL(background_image);
            setImageUrl(url);
            return () => URL.revokeObjectURL(url);
        }
        // Fallback: imagen guardada en el servidor (diseño cargado sin re-subir archivo)
        if (background_mode === 'image' && savedBgUrl) {
            setImageUrl(resolveMediaUrl(savedBgUrl));
            return undefined;
        }
        setImageUrl(null);
        return undefined;
    }, [background_mode, background_image, savedBgUrl]);

    // ── Logo from BusinessBranding ──────────────────────────────────────────
    const brandingQuery = useBusinessBrandingQuery();
    const resolvedLogoUrl = (() => {
        if (!include_logo || logo_variant === 'none') return null;
        const branding = brandingQuery.data;
        if (!branding) return null;
        if (logo_variant === 'horizontal') return branding.logo_horizontal_url ?? null;
        if (logo_variant === 'square') return branding.logo_square_url ?? null;
        // 'default': horizontal first, fallback to square
        return branding.logo_horizontal_url ?? branding.logo_square_url ?? null;
    })();

    const hasImageBg = background_mode === 'image' && imageUrl !== null;
    const dark = hasImageBg || isColorDark(background_color);
    // Auto-contrast colours (mirrors backend _text_colors logic)
    const autoMainColor = dark ? '#FFFFFF' : '#111827';
    const autoSubColor  = dark ? '#D1D5DB' : '#64748B';
    const textColor     = main_text_color ?? autoMainColor;
    const subtitleColor = subtitle_text_color ?? autoSubColor;
    const placeholderBg = dark ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.08)';

    // Outline text-shadow — approximation: 4-corner shadows simulate stroke
    const outlinePx = text_outline_width >= 0.6 ? 2 : 1;
    function buildOutlineShadow(color: string): string {
        const p = outlinePx;
        return `-${p}px -${p}px 0 ${color}, ${p}px -${p}px 0 ${color}, -${p}px ${p}px 0 ${color}, ${p}px ${p}px 0 ${color}`;
    }
    const mainTextShadow  = main_text_outline_enabled ? buildOutlineShadow(main_text_outline_color) : undefined;
    const subTextShadow   = subtitle_text_outline_enabled ? buildOutlineShadow(subtitle_text_outline_color) : undefined;

    // Font class map (mirrors FONT_MAP on backend) — legacy fallback
    const TITLE_FONT_CLASS: Record<string, string> = {
        sans_bold:  'font-sans font-bold',
        serif_bold: 'font-serif font-bold',
        mono_bold:  'font-mono font-bold',
    };
    const titleFontClass = TITLE_FONT_CLASS[title_font] ?? 'font-sans font-bold';

    // Nueva tipografía avanzada: font_family + font_weight toman precedencia
    const activeFontFamily = font_family ? getPosterFontFamily(font_family) : undefined;
    const activeFontWeight = activeFontFamily
        ? resolvePosterFontWeight(activeFontFamily, font_weight)
        : undefined;

    // Inline style para el texto principal cuando se usa el sistema avanzado
    const titleFontStyle: React.CSSProperties | undefined = activeFontFamily
        ? { fontFamily: activeFontFamily.cssFamily, fontWeight: activeFontWeight?.cssWeight }
        : undefined;

    // Ancho fijo de preview; alto se deriva del aspecto
    const PREVIEW_W = 240;
    const PREVIEW_H = Math.round(PREVIEW_W / aspectRatio);

    const isLandscape = aspectRatio > 1;
    const useQrLeft = template_code === 'qr_left' && isLandscape;
    const isBoldCta = template_code === 'bold_cta';
    const useQrWhiteBox = isBoldCta || hasImageBg;

    const TEXT_SPACING_GAP: Record<string, number> = { tight: 0, normal: 4, loose: 9 };
    const spacingGap = TEXT_SPACING_GAP[text_spacing ?? 'normal'] ?? 4;
    const displayMainText = (uppercase_mode === 'title' || uppercase_mode === 'all')
        ? (main_text || 'Texto principal').toUpperCase()
        : (main_text || 'Texto principal');
    const displaySubtitle = uppercase_mode === 'all'
        ? (subtitle ?? '').toUpperCase()
        : (subtitle ?? '');

    // ── QR size and position (new fields) ─────────────────────────────────────
    const pxPerMm = PREVIEW_W / (sizeInfo?.widthMm ?? 210);
    const resolvedQrSizeMm = resolveQrSizeMm(payload);
    // Clamp QR size so it never exceeds ~85% of the preview width
    const qrSizePx = Math.min(Math.max(resolvedQrSizeMm * pxPerMm, 14), PREVIEW_W * 0.85);
    const resolvedBottomOffsetMm = qr_bottom_offset_mm ?? QR_BOTTOM_OFFSET_MM_DEFAULT;
    const qrBottomOffsetPx = resolvedBottomOffsetMm * pxPerMm;
    const qrVAlign = qr_vertical_align ?? 'center';

    // White-box padding (mirrors backend QR_BOX_PADDING)
    const qrBoxPadding = useQrWhiteBox ? 5 : 2;
    const qrBoxBorderRadius = useQrWhiteBox ? 8 : 4;

    /** Returns absolute positioning style for the QR in vertical layouts. */
    function getQrAbsoluteStyle(): React.CSSProperties {
        const halfBox = qrSizePx / 2 + qrBoxPadding;
        const centerX = PREVIEW_W / 2 - halfBox;
        if (qrVAlign === 'bottom') {
            return {
                left: centerX,
                bottom: qrBottomOffsetPx,
            };
        }
        if (qrVAlign === 'top') {
            // Place QR near the top (after logo space)
            const topOffset = include_logo ? 14 : 6;
            return {
                left: centerX,
                top: topOffset,
            };
        }
        // 'center': vertically centered in the poster
        return {
            left: centerX,
            top: PREVIEW_H / 2 - halfBox,
        };
    }

    // ── Logo absolute positioning ─────────────────────────────────────────────
    const resolvedLogoPos = logo_position ?? 'top-center';
    const logoMarginPx = (logo_margin_mm ?? LOGO_MARGIN_MM_DEFAULT) * pxPerMm;
    // Logo max dimensions (preview scale)
    const logoMaxW = logo_variant === 'square' ? 24 : 56;
    const logoMaxH = logo_variant === 'square' ? 24 : 20;
    // For vertical layouts: inline logo when position is top-*; absolute otherwise
    const isLogoTop = resolvedLogoPos.startsWith('top');

    function getLogoAbsoluteStyle(): React.CSSProperties {
        const style: React.CSSProperties = { position: 'absolute', zIndex: 5 };
        if (resolvedLogoPos.startsWith('top')) {
            style.top = logoMarginPx;
        } else if (resolvedLogoPos.startsWith('bottom')) {
            style.bottom = logoMarginPx;
        } else {
            // middle-left / middle-right
            style.top = '50%';
            style.transform = 'translateY(-50%)';
        }
        if (resolvedLogoPos.endsWith('left')) {
            style.left = logoMarginPx;
        } else if (resolvedLogoPos.endsWith('right')) {
            style.right = logoMarginPx;
        } else {
            // center (top-center / bottom-center)
            style.left = '50%';
            style.transform = resolvedLogoPos.startsWith('middle')
                ? 'translate(-50%, -50%)'
                : 'translateX(-50%)';
        }
        return style;
    }

    function getInlineLogoContainerStyle(): React.CSSProperties {
        const justify = resolvedLogoPos.endsWith('left')
            ? 'flex-start'
            : resolvedLogoPos.endsWith('right')
                ? 'flex-end'
                : 'center';
        return {
            display: 'flex',
            justifyContent: justify,
            marginBottom: 4,
            marginTop: logoMarginPx,
        };
    }

    /** Logo content (img or placeholder rectangle). */
    // LogoContent is defined at module level; use logoProps helper to pass values.
    const logoProps: LogoContentProps = { resolvedLogoUrl, logoMaxW, logoMaxH, placeholderBg };

    return (
        <div className="flex flex-col items-center gap-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Vista previa aproximada
            </p>

            <div
                className="relative overflow-hidden rounded-xl shadow-lg"
                style={{
                    width: PREVIEW_W,
                    height: PREVIEW_H,
                    ...(hasImageBg
                        ? {
                            backgroundImage: `url("${imageUrl}")`,
                            backgroundSize: 'cover' as const,
                            backgroundPosition: 'center' as const,
                          }
                        : { backgroundColor: background_color }),
                    border: '1px solid rgba(0,0,0,0.10)',
                    maxWidth: '100%',
                }}
            >
                {/* Overlay oscuro sobre imagen de fondo */}
                {hasImageBg && (
                    <div
                        className="absolute inset-0"
                        style={{ background: 'rgba(0,0,0,0.45)', zIndex: 1 }}
                    />
                )}
                <div className="relative h-full" style={{ zIndex: 2 }}>
                {useQrLeft ? (
                    // ── Layout dos columnas (qr_left + landscape) ───────────────
                    <div className="flex h-full">
                        {/* Columna izquierda: QR — tamaño controlado por qrSizePx */}
                        <div className="flex w-[45%] items-center justify-center p-3">
                            <div
                                style={{
                                    padding: qrBoxPadding,
                                    border: useQrWhiteBox ? 'none' : `1px solid ${dark ? 'rgba(255,255,255,0.25)' : 'rgba(0,0,0,0.12)'}`,
                                    borderRadius: qrBoxBorderRadius,
                                    backgroundColor: useQrWhiteBox ? '#FFFFFF' : 'transparent',
                                    boxShadow: useQrWhiteBox ? '0 1px 6px rgba(0,0,0,0.18)' : 'none',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                }}
                            >
                                <QrPlaceholderIcon
                                    size={Math.min(qrSizePx, PREVIEW_W * 0.38)}
                                    dark={useQrWhiteBox ? false : dark}
                                />
                            </div>
                        </div>

                        {/* Columna derecha: texto (logo manejado por posicionamiento absoluto) */}
                        <div className="flex w-[55%] flex-col items-start justify-center px-2 py-3" style={{ gap: spacingGap }}>
                            <p
                                className={`line-clamp-3 text-left leading-tight ${titleFontStyle ? '' : titleFontClass}`}
                                style={{ fontSize: 7, color: textColor, textShadow: mainTextShadow, ...titleFontStyle }}
                            >
                                {displayMainText}
                            </p>
                            {displaySubtitle && (
                                <p
                                    className={`line-clamp-2 text-left leading-tight ${titleFontStyle ? '' : titleFontClass}`}
                                    style={{ fontSize: 5.5, color: subtitleColor, textShadow: subTextShadow, ...titleFontStyle }}
                                >
                                    {displaySubtitle}
                                </p>
                            )}
                        </div>
                    </div>
                ) : (
                    // ── Layout vertical (simple_centered / bold_cta / portrait) ─
                    // QR se posiciona con absolute para respetar qr_vertical_align.
                    // El bloque de texto queda en flujo normal (parte superior).
                    <div className="relative h-full p-3">
                        {/* Logo inline — solo para posiciones 'top-*' (forma parte del flujo) */}
                        {include_logo && logo_variant !== 'none' && isLogoTop && (
                            <div style={getInlineLogoContainerStyle()}>
                                <LogoContent {...logoProps} />
                            </div>
                        )}

                        {/* Bloque de texto — centrado horizontalmente, en la parte superior */}
                        <div className="flex flex-col items-center px-2 text-center" style={{ gap: spacingGap }}>
                            <p
                                className={`line-clamp-3 leading-tight ${titleFontStyle ? '' : titleFontClass}`}
                                style={{
                                    fontSize: isBoldCta ? 10 : 8,
                                    color: textColor,
                                    textShadow: mainTextShadow,
                                    ...titleFontStyle,
                                }}
                            >
                                {displayMainText}
                            </p>
                            {displaySubtitle && (
                                <p
                                    className={`line-clamp-2 leading-tight ${titleFontStyle ? '' : titleFontClass}`}
                                    style={{ fontSize: 6, color: subtitleColor, textShadow: subTextShadow, ...titleFontStyle }}
                                >
                                    {displaySubtitle}
                                </p>
                            )}
                        </div>

                        {/* QR con posición controlada por qr_vertical_align */}
                        <QrBlock
                            style={getQrAbsoluteStyle()}
                            qrBoxPadding={qrBoxPadding}
                            useQrWhiteBox={useQrWhiteBox}
                            qrBoxBorderRadius={qrBoxBorderRadius}
                            qrSizePx={qrSizePx}
                            dark={dark}
                        />
                    </div>
                )}

                {/* Logo absolutamente posicionado:
                    - siempre para qr_left (ambos layouts)
                    - solo para posiciones no-top en vertical */}
                {include_logo && logo_variant !== 'none' && (useQrLeft || !isLogoTop) && (
                    <div style={getLogoAbsoluteStyle()}>
                        <LogoContent {...logoProps} />
                    </div>
                )}
                </div>
            </div>

            <p className="text-center text-xs text-slate-400">
                {sizeInfo?.label} · {sizeInfo?.description}
            </p>
        </div>
    );
}

/** Ícono SVG que simula la apariencia visual de un QR. */
function QrPlaceholderIcon({ size, dark }: { size: number; dark: boolean }) {
    const color = dark ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.72)';
    const s = Math.max(size, 28);
    return (
        <svg
            width={s}
            height={s}
            viewBox="0 0 40 40"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            aria-label="Código QR"
        >
            {/* Finder: superior izquierdo */}
            <rect x="2" y="2" width="14" height="14" rx="2" stroke={color} strokeWidth="2" fill="none" />
            <rect x="5" y="5" width="8" height="8" rx="1" fill={color} />
            {/* Finder: superior derecho */}
            <rect x="24" y="2" width="14" height="14" rx="2" stroke={color} strokeWidth="2" fill="none" />
            <rect x="27" y="5" width="8" height="8" rx="1" fill={color} />
            {/* Finder: inferior izquierdo */}
            <rect x="2" y="24" width="14" height="14" rx="2" stroke={color} strokeWidth="2" fill="none" />
            <rect x="5" y="27" width="8" height="8" rx="1" fill={color} />
            {/* Datos simulados */}
            <rect x="24" y="24" width="3" height="3" rx="0.5" fill={color} />
            <rect x="29" y="24" width="3" height="3" rx="0.5" fill={color} />
            <rect x="34" y="24" width="3" height="3" rx="0.5" fill={color} />
            <rect x="24" y="29" width="3" height="3" rx="0.5" fill={color} />
            <rect x="34" y="29" width="3" height="3" rx="0.5" fill={color} />
            <rect x="29" y="34" width="3" height="3" rx="0.5" fill={color} />
            <rect x="34" y="34" width="3" height="3" rx="0.5" fill={color} />
        </svg>
    );
}
