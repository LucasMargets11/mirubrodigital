'use client';

import type {
  FontPreset,
  FontSizeOption,
  LayoutStyle,
  LogoSize,
  LogoVariant,
  PrintableCardSize,
  PrintableTemplateCode,
  TextTransform,
  HeaderContentType,
} from '../types';

/** Texto de encabezado por defecto que muestra cada template promo en el PDF. */
const PROMO_BADGE: Partial<Record<PrintableTemplateCode, string>> = {
  promo_offer:     'OFERTA',
  promo_discount:  'DESCUENTO',
  promo_2x1:       '2x1',
  promo_combo:     'COMBO',
  promo_clearance: 'LIQUIDACIÓN',
  promo_weekly:    'PROMO SEMANAL',
};

type PrintPreviewProps = {
  title: string;
  price: string;
  includePrice: boolean;
  logoVariant: LogoVariant;
  cardSize: PrintableCardSize;
  showCutLines: boolean;
  accentColor?: string;
  logoUrl?: string | null;
  promoText?: string;
  oldPrice?: string;
  templateCode?: PrintableTemplateCode;
  // Phase 4
  layoutStyle?: LayoutStyle;
  fontPreset?: FontPreset;
  logoSize?: LogoSize;
  // Phase 5
  titleFontSize?: FontSizeOption;
  priceFontSize?: FontSizeOption;
  secondaryFontSize?: FontSizeOption;
  // Phase 6: content frame
  contentFrameEnabled?: boolean;
  contentFrameColor?: string;
  contentFrameWidth?: number;
  contentFramePadding?: number;   // cm — space between cut line and frame
  contentInnerPadding?: number;   // cm — space between frame and text
  // Phase 7: text transform
  textTransform?: TextTransform;
  // Phase 8: zona superior
  headerContentType?: HeaderContentType;
  headerText?: string;
  // Phase 9: colores y espaciado
  headerTextColor?: string;
  titleTextColor?: string;
  priceTextColor?: string;
  priceGapPt?: number;
};

/** px per cm for the preview */
const PREVIEW_PX_PER_CM = 14;
const MAX_PREVIEW_W = 210; // px cap

export function PrintPreview({
  title,
  price,
  includePrice,
  logoVariant,
  cardSize,
  showCutLines,
  accentColor = '#1e293b',
  logoUrl,
  promoText,
  oldPrice,
  templateCode,
  layoutStyle = 'centered_product',
  fontPreset = 'bold',
  logoSize = 'medium',
  titleFontSize = 'medium',
  priceFontSize = 'large',
  secondaryFontSize = 'small',
  contentFrameEnabled = true,
  contentFrameColor = '#000000',
  contentFrameWidth = 2,
  contentFramePadding = 0.4,
  contentInnerPadding = 0.3,
  textTransform = 'none',
  headerContentType = 'logo',
  headerText = '',
  headerTextColor = '#DC2626',
  titleTextColor = '#111827',
  priceTextColor = '#000000',
  priceGapPt = 10,
}: PrintPreviewProps) {
  const rawW = Math.round(cardSize.widthCm * PREVIEW_PX_PER_CM);
  const rawH = Math.round(cardSize.heightCm * PREVIEW_PX_PER_CM);

  const scale = rawW > MAX_PREVIEW_W ? MAX_PREVIEW_W / rawW : 1;
  const w = Math.round(rawW * scale);
  const h = Math.round(rawH * scale);

  // Promo badge: use explicit promoText first, then template default
  const promoBadge = promoText || (templateCode ? (PROMO_BADGE[templateCode] ?? null) : null);
  const showLogo = headerContentType === 'logo' && logoVariant !== 'none' && Boolean(logoUrl) && layoutStyle !== 'minimal_label';
  const effectiveHeaderText = headerContentType === 'highlight_text'
    ? (headerText || promoBadge || '')
    : '';

  // Phase 7: text transform helper (NOT applied to price)
  const applyT = (s: string) => textTransform === 'uppercase' ? s.toUpperCase() : s;

  // Font family from preset
  const fontFamily =
    fontPreset === 'elegant'
      ? 'Times New Roman, Times, serif'
      : fontPreset === 'condensed'
        ? 'Courier New, Courier, monospace'
        : 'Helvetica Neue, Helvetica, Arial, sans-serif';

  // Cut line border (outer container)
  const cutLineBorder: React.CSSProperties['border'] = showCutLines
    ? '1.5px dashed #cbd5e1'
    : '1.5px solid #e2e8f0';

  // Content frame border
  const contentFrameBorder: React.CSSProperties['border'] = contentFrameEnabled
    ? `${Math.max(1, Math.round(contentFrameWidth * 0.4))}px solid ${contentFrameColor}`
    : 'none';

  // Padding values in px
  const framePadPx = Math.max(2, contentFramePadding * PREVIEW_PX_PER_CM * scale);
  const innerPadPx = Math.max(2, contentInnerPadding * PREVIEW_PX_PER_CM * scale);

  // Logo max-height ratio
  const _logoRatios: Record<LogoSize, number> = { small: 0.10, medium: 0.18, large: 0.26, xlarge: 0.36 };
  const logoHeightRatio = _logoRatios[logoSize] ?? 0.18;

  // Font sizes: proportional to text area width
  const textW = w - 2 * framePadPx - 2 * innerPadPx;
  const _titleSzMap: Record<FontSizeOption, number> = { small: 0.06, medium: 0.10, large: 0.15, xlarge: 0.20 };
  const _priceSzMap: Record<FontSizeOption, number> = { small: 0.08, medium: 0.13, large: 0.20, xlarge: 0.28 };
  const _secSzMap:   Record<FontSizeOption, number> = { small: 0.05, medium: 0.08, large: 0.12, xlarge: 0.16 };
  const isPromoTemplate = templateCode?.startsWith('promo_') ?? false;
  const titleXlargeBoost = isPromoTemplate && titleFontSize === 'xlarge' ? 1.5 : 1;
  const titlePx = Math.max(7, textW * (_titleSzMap[titleFontSize] ?? 0.10) * titleXlargeBoost);
  const pricePx = layoutStyle === 'price_focus'
    ? Math.max(8, textW * (_priceSzMap[priceFontSize] ?? 0.13) * 1.5)
    : Math.max(8, textW * (_priceSzMap[priceFontSize] ?? 0.13));
  const secPx   = Math.max(6, textW * (_secSzMap[secondaryFontSize] ?? 0.08));
  // Phase 9: gap between title and price in px (PDF uses points; 1pt ≈ 0.035cm)
  const priceGapPx = Math.round(priceGapPt * scale * PREVIEW_PX_PER_CM * 0.035);

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-slate-700">Vista previa orientativa</p>
      <p className="text-xs text-slate-400">
        El resultado final puede diferir del diseño real del PDF.
      </p>

      <div className="flex justify-center">
        {/* Outer card: cut line + frame padding zone */}
        <div
          style={{
            width: w,
            height: h,
            border: cutLineBorder,
            borderRadius: 4,
            backgroundColor: '#ffffff',
            display: 'flex',
            flexDirection: 'column',
            padding: framePadPx,
            boxSizing: 'border-box',
            fontFamily,
            overflow: 'hidden',
          }}
        >
          {/* Header zone: logo / highlight_text / none (outside content frame) */}
          {showLogo && logoUrl ? (
            <div style={{ flexShrink: 0, display: 'flex', justifyContent: 'center', marginBottom: 2 }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={logoUrl}
                alt="Logo"
                style={{ maxHeight: h * logoHeightRatio, maxWidth: w * 0.7, objectFit: 'contain' }}
              />
            </div>
          ) : headerContentType === 'highlight_text' && effectiveHeaderText ? (
            <div style={{ flexShrink: 0, display: 'flex', justifyContent: 'center', marginBottom: 2 }}>
              {layoutStyle === 'promo_badge' ? (
                <span
                  style={{
                    fontSize: titlePx * 0.85,
                    fontWeight: 'bold',
                    color: '#ffffff',
                    backgroundColor: headerTextColor,
                    borderRadius: 3,
                    padding: '1px 5px',
                    textAlign: 'center',
                  }}
                >
                  {applyT(effectiveHeaderText)}
                </span>
              ) : (
                <p
                  style={{
                    fontSize: titlePx * 0.85,
                    fontWeight: 'bold',
                    color: headerTextColor,
                    textAlign: 'center',
                    margin: 0,
                  }}
                >
                  {applyT(effectiveHeaderText)}
                </p>
              )}
            </div>
          ) : null}

          {/* Content frame: surrounds text block only */}
          <div
            style={{
              flex: 1,
              border: contentFrameBorder,
              padding: innerPadPx,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
              gap: 2,
              minHeight: 0,
              boxSizing: 'border-box',
            }}
          >
            {/* Promo badge: inside frame only when NOT used as header */}
            {promoBadge && headerContentType !== 'highlight_text' ? (
              layoutStyle === 'promo_badge' ? (
                <span
                  style={{
                    fontSize: titlePx,
                    fontWeight: 'bold',
                    color: '#ffffff',
                    backgroundColor: '#dc2626',
                    borderRadius: 3,
                    padding: '1px 5px',
                    textAlign: 'center',
                  }}
                >
                  {applyT(promoBadge)}
                </span>
              ) : (
                <p
                  style={{
                    fontSize: titlePx,
                    fontWeight: 'bold',
                    color: '#dc2626',
                    textAlign: 'center',
                    overflow: 'hidden',
                  }}
                >
                  {applyT(promoBadge)}
                </p>
              )
            ) : null}

            {/* Title */}
            <p
              style={{
                fontSize: titlePx,
                fontWeight: 'bold',
                color: titleTextColor,
                textAlign: 'center',
                overflow: 'hidden',
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
              }}
            >
              {applyT(title || 'Nombre del producto')}
            </p>

            {/* Prices */}
            {includePrice && (
              <>
                {oldPrice ? (
                  <p
                    style={{
                      fontSize: secPx,
                      color: '#94a3b8',
                      textDecoration: 'line-through',
                      textAlign: 'center',
                      marginTop: priceGapPx,
                    }}
                  >
                    $ {oldPrice}
                  </p>
                ) : null}
                <p
                  style={{
                    fontSize: pricePx,
                    fontWeight: 'bold',
                    color: layoutStyle === 'price_focus' ? accentColor : priceTextColor,
                    textAlign: 'center',
                    marginTop: oldPrice ? 0 : priceGapPx,
                  }}
                >
                  {price || '$ -'}
                </p>
              </>
            )}
          </div>
        </div>
      </div>

      <p className="text-center text-xs text-slate-400">
        {cardSize.widthCm} × {cardSize.heightCm} cm
      </p>
    </div>
  );
}

