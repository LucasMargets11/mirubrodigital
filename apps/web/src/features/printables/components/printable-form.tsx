'use client';

import { useCallback, useState } from 'react';

import { useBusinessBrandingQuery } from '@/features/gestion/hooks';
import type { Product } from '@/features/gestion/types';
import { Switch } from '@/components/ui/switch';

import {
  DEFAULT_CARD_SIZE,
  DEFAULT_HEADER_TEXT_COLOR,
  DEFAULT_PRICE_GAP_PT,
  DEFAULT_PRICE_TEXT_COLOR,
  DEFAULT_TITLE_TEXT_COLOR,
  FONT_PRESET_OPTIONS,
  FONT_SIZE_OPTIONS,
  HEADER_CONTENT_OPTIONS,
  LAYOUT_STYLE_OPTIONS,
  LOGO_SIZE_OPTIONS,
  MAX_COPIES_PER_ITEM,
  PRINTABLE_TEMPLATES,
  TEXT_COLOR_OPTIONS,
  TEXT_TRANSFORM_OPTIONS,
} from '../constants';
import { useGeneratePrintablePdf } from '../hooks';
import type {
  FontPreset,
  FontSizeOption,
  GeneratePrintablePdfPayload,
  HeaderContentType,
  LayoutStyle,
  LogoSize,
  LogoVariant,
  PrintableCardSize,
  PrintableTemplateCode,
  PrintableType,
  TextTransform,
} from '../types';
import { DEFAULT_TEMPLATE_FOR_TYPE } from '../types';

import { CardSizeSelector } from './card-size-selector';
import { GeneratePdfButton } from './generate-pdf-button';
import { LogoSelector } from './logo-selector';
import { PriceVisibilitySwitch } from './price-visibility-switch';
import { PrintPreview } from './print-preview';
import { ProductPicker } from './product-picker';
import { TemplateSelector } from './template-selector';

export function PrintableForm() {
  const { generate, isLoading, error, clearError } = useGeneratePrintablePdf();
  const brandingQuery = useBusinessBrandingQuery();
  const branding = brandingQuery.data;

  // ── Type + template state ──────────────────────────────────────────────────
  const [printableType, setPrintableType] = useState<PrintableType>('product');
  const [selectedTemplate, setSelectedTemplate] = useState<PrintableTemplateCode>(
    DEFAULT_TEMPLATE_FOR_TYPE['product'],
  );

  // ── Product-mode state ────────────────────────────────────────────────────
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [title, setTitle] = useState('');
  const [price, setPrice] = useState('');
  const [copies, setCopies] = useState(1);

  // ── Promotion-mode state ──────────────────────────────────────────────────
  const [promoProduct, setPromoProduct] = useState<Product | null>(null);
  const [promoTitle, setPromoTitle] = useState('');
  const [promoText, setPromoText] = useState('');
  const [promoDescription, setPromoDescription] = useState('');
  const [promoPrice, setPromoPrice] = useState('');
  const [promoOldPrice, setPromoOldPrice] = useState('');
  const [promoCopies, setPromoCopies] = useState(1);

  // ── Shared design state ───────────────────────────────────────────────────
  const [cardSize, setCardSize] = useState<PrintableCardSize>(DEFAULT_CARD_SIZE);
  const [logoVariant, setLogoVariant] = useState<LogoVariant>('none');
  const [includePrice, setIncludePrice] = useState(true);
  const [showCutLines, setShowCutLines] = useState(true);

  // ── Diseño visual ─────────────────────────────────────────────────────────
  const [layoutStyle, setLayoutStyle] = useState<LayoutStyle>('centered_product');
  const [fontPreset, setFontPreset] = useState<FontPreset>('bold');
  const [logoSize, setLogoSize] = useState<LogoSize>('medium');
  // ── Tipografía ────────────────────────────────────────────────────────────
  const [titleFontSize, setTitleFontSize] = useState<FontSizeOption>('medium');
  const [priceFontSize, setPriceFontSize] = useState<FontSizeOption>('large');
  const [secondaryFontSize, setSecondaryFontSize] = useState<FontSizeOption>('small');
  // ── Marco de contenido (Phase 6) ──────────────────────────────────────────
  const [contentFrameEnabled, setContentFrameEnabled] = useState(true);
  const [contentFrameColor, setContentFrameColor] = useState('#000000');
  const [contentFrameWidth, setContentFrameWidth] = useState(2);
  const [contentFramePadding, setContentFramePadding] = useState(0.4);
  const [contentInnerPadding, setContentInnerPadding] = useState(0.3);
  // ── Transformación de texto (Phase 7) ─────────────────────────────────────
  const [textTransform, setTextTransform] = useState<TextTransform>('none');
  const [headerContentType, setHeaderContentType] = useState<HeaderContentType>('logo');
  const [headerText, setHeaderText] = useState('');
  // ── Colores y espaciado (Phase 9) ─────────────────────────────────────────
  const [headerTextColor, setHeaderTextColor] = useState(DEFAULT_HEADER_TEXT_COLOR);
  const [titleTextColor, setTitleTextColor] = useState(DEFAULT_TITLE_TEXT_COLOR);
  const [priceTextColor, setPriceTextColor] = useState(DEFAULT_PRICE_TEXT_COLOR);
  const [priceGapPt, setPriceGapPt] = useState(DEFAULT_PRICE_GAP_PT);
  // ── Handlers ──────────────────────────────────────────────────────────────
  const handleTypeChange = useCallback(
    (newType: PrintableType) => {
      setPrintableType(newType);
      setSelectedTemplate(DEFAULT_TEMPLATE_FOR_TYPE[newType]);
      setHeaderContentType(newType === 'promotion' ? 'highlight_text' : 'logo');
      clearError();
    },
    [clearError],
  );

  const handleProductSelect = useCallback((product: Product | null) => {
    setSelectedProduct(product);
    if (product) {
      setTitle(textTransform === 'uppercase' ? product.name.toUpperCase() : product.name);
      setPrice(product.price ?? '');
    }
  }, [textTransform]);

  const handlePromoProductSelect = useCallback(
    (product: Product | null) => {
      setPromoProduct(product);
      if (product && !promoTitle) {
        setPromoTitle(product.name);
      }
    },
    [promoTitle],
  );

  // Derive logo URL for preview
  const logoUrl =
    logoVariant === 'horizontal'
      ? branding?.logo_horizontal_url
      : logoVariant === 'square'
        ? branding?.logo_square_url
        : logoVariant === 'default'
          ? (branding?.logo_horizontal_url ?? branding?.logo_square_url)
          : null;

  const handleGenerate = useCallback(() => {
    clearError();

    if (printableType === 'promotion') {
      const payload: GeneratePrintablePdfPayload = {
        type: 'promotion',
        template_code: selectedTemplate,
        paper_size: 'A4',
        card_size: { width_cm: cardSize.widthCm, height_cm: cardSize.heightCm },
        logo_variant: logoVariant,
        include_logo: headerContentType === 'logo' && logoVariant !== 'none',
        include_price: includePrice,
        show_cut_lines: showCutLines,
        layout_style: layoutStyle,
        font_preset: fontPreset,
        logo_size: logoSize,
        logo_position: 'top_center',
        title_font_size: titleFontSize,
        price_font_size: priceFontSize,
        secondary_font_size: secondaryFontSize,
        content_frame_enabled: contentFrameEnabled,
        content_frame_color: contentFrameColor,
        content_frame_width: contentFrameWidth,
        content_frame_padding_cm: contentFramePadding,
        content_inner_padding_cm: contentInnerPadding,
        text_transform: textTransform,
        header_content_type: headerContentType,
        header_text: headerContentType === 'highlight_text'
          ? (headerText.trim() || promoText.trim() || undefined)
          : undefined,
        header_text_color: headerTextColor,
        title_text_color: titleTextColor,
        price_text_color: priceTextColor,
        price_gap_pt: priceGapPt,
        items: [
          {
            product_id: promoProduct?.id ?? null,
            title: promoTitle.trim(),
            description: promoDescription.trim() || undefined,
            promo_text: promoText.trim() || undefined,
            ...(includePrice && promoPrice ? { price: promoPrice } : {}),
            ...(includePrice && promoOldPrice ? { old_price: promoOldPrice } : {}),
            copies: promoCopies,
          },
        ],
      };
      void generate(payload);
      return;
    }

    if (copies < 1 || copies > MAX_COPIES_PER_ITEM) return;

    const payload: GeneratePrintablePdfPayload = {
      type: 'product',
      template_code: selectedTemplate,
      paper_size: 'A4',
      card_size: { width_cm: cardSize.widthCm, height_cm: cardSize.heightCm },
      logo_variant: logoVariant,
      include_logo: headerContentType === 'logo' && logoVariant !== 'none',
      include_price: includePrice,
      show_cut_lines: showCutLines,
      layout_style: layoutStyle,
      font_preset: fontPreset,
      logo_size: logoSize,
      logo_position: 'top_center',
      title_font_size: titleFontSize,
      price_font_size: priceFontSize,
      secondary_font_size: secondaryFontSize,
      content_frame_enabled: contentFrameEnabled,
      content_frame_color: contentFrameColor,
      content_frame_width: contentFrameWidth,
      content_frame_padding_cm: contentFramePadding,
      content_inner_padding_cm: contentInnerPadding,
      text_transform: textTransform,
      header_content_type: headerContentType,
      header_text: headerContentType === 'highlight_text'
        ? (headerText.trim() || undefined)
        : undefined,
      header_text_color: headerTextColor,
      title_text_color: titleTextColor,
      price_text_color: priceTextColor,
      price_gap_pt: priceGapPt,
      items: [
        {
          product_id: selectedProduct?.id ?? null,
          title: (title.trim() || selectedProduct?.name) ?? '',
          ...(includePrice ? { price: price || undefined } : {}),
          copies,
        },
      ],
    };
    void generate(payload);
  }, [
    generate,
    clearError,
    printableType,
    selectedTemplate,
    cardSize,
    logoVariant,
    includePrice,
    showCutLines,
    selectedProduct,
    title,
    price,
    copies,
    promoProduct,
    promoTitle,
    promoDescription,
    promoText,
    promoPrice,
    promoOldPrice,
    promoCopies,
    layoutStyle,
    fontPreset,
    logoSize,
    titleFontSize,
    priceFontSize,
    secondaryFontSize,
    contentFrameEnabled,
    contentFrameColor,
    contentFrameWidth,
    contentFramePadding,
    contentInnerPadding,
    textTransform,
    headerContentType,
    headerText,
    headerTextColor,
    titleTextColor,
    priceTextColor,
    priceGapPt,
  ]);

  const copiesInvalid =
    printableType === 'product' && (copies < 1 || copies > MAX_COPIES_PER_ITEM);
  const canGenerate =
    printableType === 'promotion'
      ? promoTitle.trim().length > 0
      : (title.trim().length > 0 || Boolean(selectedProduct)) && !copiesInvalid;

  // Derive preview data
  const templateLabel =
    PRINTABLE_TEMPLATES.find((t) => t.code === selectedTemplate)?.label ?? '';
  const previewTitle =
    printableType === 'promotion'
      ? promoTitle || promoText || ''
      : title || selectedProduct?.name || '';
  const previewPrice = printableType === 'promotion' ? promoPrice : price;
  const previewOldPrice = printableType === 'promotion' ? promoOldPrice : undefined;
  const previewPromoText = printableType === 'promotion' ? promoText : undefined;

  return (
    <div className="space-y-4">
      {/* Selector de tipo */}
      <div className="flex gap-1 rounded-xl border border-slate-200 bg-slate-50 p-1 w-fit">
        {(['product', 'promotion'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => handleTypeChange(t)}
            className={[
              'rounded-lg px-4 py-2 text-sm font-medium transition-colors',
              printableType === t
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-700',
            ].join(' ')}
          >
            {t === 'product' ? 'Cartel de producto' : 'Cartel promocional'}
          </button>
        ))}
      </div>

      {/* Selector de template (solo visible para promotion, que tiene 6 opciones) */}
      <TemplateSelector
        type={printableType}
        value={selectedTemplate}
        onChange={setSelectedTemplate}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* ── Columna izquierda: formulario ─────────────────────────────── */}
        <div className="space-y-6">
          {/* Contenido del cartel */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
            <h3 className="text-sm font-semibold text-slate-900">
              {printableType === 'promotion' ? 'Datos de la promoción' : 'Contenido del cartel'}
            </h3>

            {printableType === 'product' ? (
              /* ── Modo producto ── */
              <>
                <ProductPicker onSelect={handleProductSelect} selected={selectedProduct} />

                <div className="space-y-1.5">
                  <label htmlFor="cartel-title" className="text-sm font-medium text-slate-700">
                    Título <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="cartel-title"
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="Nombre del producto o cartel"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900/20"
                    maxLength={120}
                  />
                </div>

                {includePrice && (
                  <div className="space-y-1.5">
                    <label htmlFor="cartel-price" className="text-sm font-medium text-slate-700">
                      Precio
                    </label>
                    <input
                      id="cartel-price"
                      type="text"
                      value={price}
                      onChange={(e) => setPrice(e.target.value)}
                      placeholder="$ 0.00"
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900/20"
                    />
                  </div>
                )}
              </>
            ) : (
              /* ── Modo promoción ── */
              <>
                {/* ProductPicker opcional */}
                <div>
                  <p className="mb-1.5 text-xs text-slate-500">
                    Producto asociado{' '}
                    <span className="text-slate-400">(opcional)</span>
                  </p>
                  <ProductPicker onSelect={handlePromoProductSelect} selected={promoProduct} />
                </div>

                {/* Título – obligatorio */}
                <div className="space-y-1.5">
                  <label htmlFor="promo-title" className="text-sm font-medium text-slate-700">
                    Título <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="promo-title"
                    type="text"
                    value={promoTitle}
                    onChange={(e) => setPromoTitle(e.target.value)}
                    placeholder="Ej. Yerba Mate, Combo Familiar…"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900/20"
                    maxLength={120}
                  />
                </div>

                {/* Texto destacado */}
                <div className="space-y-1.5">
                  <label htmlFor="promo-text" className="text-sm font-medium text-slate-700">
                    Texto destacado{' '}
                    <span className="text-xs text-slate-400">aparece en rojo · max 60 car.</span>
                  </label>
                  <input
                    id="promo-text"
                    type="text"
                    value={promoText}
                    onChange={(e) => setPromoText(e.target.value)}
                    placeholder={`Ej. ${templateLabel.toUpperCase() || 'OFERTA'}`}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900/20"
                    maxLength={60}
                  />
                  <p className="text-xs text-slate-400">
                    Si lo dejás vacío, se usará el texto predeterminado del estilo seleccionado.
                  </p>
                </div>

                {/* Descripción / aclaración */}
                <div className="space-y-1.5">
                  <label htmlFor="promo-desc" className="text-sm font-medium text-slate-700">
                    Descripción / aclaración{' '}
                    <span className="text-xs text-slate-400">opcional</span>
                  </label>
                  <input
                    id="promo-desc"
                    type="text"
                    value={promoDescription}
                    onChange={(e) => setPromoDescription(e.target.value)}
                    placeholder="Ej. Válido hasta agotar stock"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900/20"
                    maxLength={300}
                  />
                </div>

                {/* Precios (solo si include_price) */}
                {includePrice && (
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <label htmlFor="promo-old-price" className="text-sm font-medium text-slate-700">
                        Precio anterior{' '}
                        <span className="text-xs text-slate-400">tachado</span>
                      </label>
                      <input
                        id="promo-old-price"
                        type="text"
                        value={promoOldPrice}
                        onChange={(e) => setPromoOldPrice(e.target.value)}
                        placeholder="Ej. 3000"
                        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900/20"
                        maxLength={30}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label htmlFor="promo-price" className="text-sm font-medium text-slate-700">
                        Precio promocional
                      </label>
                      <input
                        id="promo-price"
                        type="text"
                        value={promoPrice}
                        onChange={(e) => setPromoPrice(e.target.value)}
                        placeholder="Ej. 2500"
                        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900/20"
                        maxLength={30}
                      />
                    </div>
                  </div>
                )}

                {/* Copias */}
                <div className="space-y-1.5">
                  <label htmlFor="promo-copies" className="text-sm font-medium text-slate-700">
                    Cantidad de copias
                  </label>
                  <input
                    id="promo-copies"
                    type="number"
                    min={1}
                    max={MAX_COPIES_PER_ITEM}
                    value={promoCopies}
                    onChange={(e) => {
                      const val = Math.min(MAX_COPIES_PER_ITEM, Math.max(1, Number(e.target.value)));
                      setPromoCopies(val);
                    }}
                    className="w-24 rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900/20"
                  />
                  <p className="text-xs text-slate-400">
                    Hasta {MAX_COPIES_PER_ITEM} copias por cartel.
                  </p>
                </div>
              </>
            )}
          </div>

          {/* ── B. Diseño ─────────────────────────────────────────────────── */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
            <h3 className="text-sm font-semibold text-slate-900">Diseño</h3>

            {/* Estilo del cartel */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Estilo del cartel</label>
              <div className="flex flex-wrap gap-1">
                {LAYOUT_STYLE_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => setLayoutStyle(o.value)}
                    className={[
                      'rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors',
                      layoutStyle === o.value
                        ? 'bg-slate-900 text-white border-slate-900'
                        : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50',
                    ].join(' ')}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Zona superior */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Zona superior</label>
              <div className="flex flex-wrap gap-1">
                {HEADER_CONTENT_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => setHeaderContentType(o.value)}
                    className={[
                      'rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors',
                      headerContentType === o.value
                        ? 'bg-slate-900 text-white border-slate-900'
                        : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50',
                    ].join(' ')}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Texto superior (solo cuando highlight_text) */}
            {headerContentType === 'highlight_text' && (
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700">Texto superior</label>
                <input
                  type="text"
                  value={headerText}
                  onChange={(e) => setHeaderText(e.target.value)}
                  placeholder={
                    printableType === 'promotion'
                      ? (promoText || 'Ej. OFERTA, COMBO\u2026')
                      : 'Ej. NUEVO, ESPECIAL\u2026'
                  }
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900/20"
                  maxLength={60}
                />
                <p className="text-xs text-slate-400">
                  Este texto se mostrar\u00e1 arriba del cartel, por fuera del marco.
                </p>
              </div>
            )}

            {/* Logo (solo cuando zona superior = Logo) */}
            {headerContentType === 'logo' && (
              <>
                <LogoSelector value={logoVariant} onChange={setLogoVariant} />
                {logoVariant !== 'none' && (
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium text-slate-700">Tama\u00f1o del logo</label>
                    <div className="flex flex-wrap gap-1">
                      {LOGO_SIZE_OPTIONS.map((o) => (
                        <button
                          key={o.value}
                          type="button"
                          onClick={() => setLogoSize(o.value)}
                          className={[
                            'rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors',
                            logoSize === o.value
                              ? 'bg-slate-900 text-white border-slate-900'
                              : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50',
                          ].join(' ')}
                        >
                          {o.label}
                        </button>
                      ))}
                    </div>
                    <p className="text-xs text-slate-400">El logo aparece fuera del marco del contenido.</p>
                  </div>
                )}
              </>
            )}
          </div>

          {/* ── C. Texto ──────────────────────────────────────────────────── */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
            <h3 className="text-sm font-semibold text-slate-900">Texto</h3>

            {/* Fuente */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Estilo de fuente</label>
              <div className="flex flex-wrap gap-1">
                {FONT_PRESET_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => setFontPreset(o.value)}
                    className={[
                      'rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors',
                      fontPreset === o.value
                        ? 'bg-slate-900 text-white border-slate-900'
                        : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50',
                    ].join(' ')}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Transformación de texto */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Transformación de texto</label>
              <div className="flex flex-wrap gap-1">
                {TEXT_TRANSFORM_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => setTextTransform(o.value)}
                    className={[
                      'rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors',
                      textTransform === o.value
                        ? 'bg-slate-900 text-white border-slate-900'
                        : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50',
                    ].join(' ')}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
              <p className="text-xs text-slate-400">
                Aplica al título, descripción y texto del cartel (no al precio).
              </p>
            </div>

            {/* Tamaño del título */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Tamaño del título</label>
              <div className="flex flex-wrap gap-1">
                {FONT_SIZE_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => setTitleFontSize(o.value)}
                    className={[
                      'rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors',
                      titleFontSize === o.value
                        ? 'bg-slate-900 text-white border-slate-900'
                        : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50',
                    ].join(' ')}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Tamaño del precio (solo si se muestra precio) */}
            {includePrice && (
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700">Tamaño del precio</label>
                <div className="flex flex-wrap gap-1">
                  {FONT_SIZE_OPTIONS.map((o) => (
                    <button
                      key={o.value}
                      type="button"
                      onClick={() => setPriceFontSize(o.value)}
                      className={[
                        'rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors',
                        priceFontSize === o.value
                          ? 'bg-slate-900 text-white border-slate-900'
                          : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50',
                      ].join(' ')}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Tamaño del texto secundario */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Texto secundario</label>
              <p className="text-xs text-slate-400">Descripción, precio anterior, aclaraciones.</p>
              <div className="flex flex-wrap gap-1">
                {FONT_SIZE_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => setSecondaryFontSize(o.value)}
                    className={[
                      'rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors',
                      secondaryFontSize === o.value
                        ? 'bg-slate-900 text-white border-slate-900'
                        : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50',
                    ].join(' ')}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Color del texto superior (solo si zona superior = texto destacado) */}
            {headerContentType === 'highlight_text' && (
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700">Color del texto superior</label>
                <div className="flex flex-wrap gap-1">
                  {TEXT_COLOR_OPTIONS.map((o) => (
                    <button
                      key={o.value}
                      type="button"
                      onClick={() => setHeaderTextColor(o.value)}
                      className={[
                        'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors',
                        headerTextColor === o.value
                          ? 'bg-slate-900 text-white border-slate-900'
                          : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50',
                      ].join(' ')}
                    >
                      <span
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: o.value, border: '1px solid rgba(0,0,0,0.15)' }}
                      />
                      {o.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Color del título */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Color del título</label>
              <div className="flex flex-wrap gap-1">
                {TEXT_COLOR_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => setTitleTextColor(o.value)}
                    className={[
                      'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors',
                      titleTextColor === o.value
                        ? 'bg-slate-900 text-white border-slate-900'
                        : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50',
                    ].join(' ')}
                  >
                    <span
                      className="w-3 h-3 rounded-full flex-shrink-0"
                      style={{ backgroundColor: o.value, border: '1px solid rgba(0,0,0,0.15)' }}
                    />
                    {o.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Color del precio + separación (solo si includePrice) */}
            {includePrice && (
              <>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-slate-700">Color del precio</label>
                  <div className="flex flex-wrap gap-1">
                    {TEXT_COLOR_OPTIONS.map((o) => (
                      <button
                        key={o.value}
                        type="button"
                        onClick={() => setPriceTextColor(o.value)}
                        className={[
                          'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors',
                          priceTextColor === o.value
                            ? 'bg-slate-900 text-white border-slate-900'
                            : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50',
                        ].join(' ')}
                      >
                        <span
                          className="w-3 h-3 rounded-full flex-shrink-0"
                          style={{ backgroundColor: o.value, border: '1px solid rgba(0,0,0,0.15)' }}
                        />
                        {o.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-slate-700">Separación título-precio</label>
                    <span className="text-xs text-slate-500">{priceGapPt} pt</span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={30}
                    step={2}
                    value={priceGapPt}
                    onChange={(e) => setPriceGapPt(Number(e.target.value))}
                    className="w-full accent-slate-900"
                  />
                </div>
              </>
            )}
          </div>

          {/* ── D. Marco ──────────────────────────────────────────────────── */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
            <h3 className="text-sm font-semibold text-slate-900">Marco del contenido</h3>
            <p className="text-xs text-slate-400">
              El marco encierra solo el bloque textual. El logo queda por fuera.
            </p>

            {/* Activar marco */}
            <div className="flex items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white px-3 py-2.5">
              <div>
                <p className="text-sm font-medium text-slate-800">Mostrar marco</p>
                <p className="text-xs text-slate-500">Dibuja un borde alrededor del texto</p>
              </div>
              <Switch checked={contentFrameEnabled} onCheckedChange={setContentFrameEnabled} />
            </div>

            {contentFrameEnabled && (
              <>
                {/* Color del marco */}
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-slate-700">Color del marco</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      value={contentFrameColor}
                      onChange={(e) => setContentFrameColor(e.target.value)}
                      className="h-8 w-10 rounded border border-slate-200 cursor-pointer"
                    />
                    <input
                      type="text"
                      value={contentFrameColor}
                      onChange={(e) => setContentFrameColor(e.target.value)}
                      placeholder="#000000"
                      maxLength={7}
                      className="w-28 rounded-lg border border-slate-200 px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-slate-900/20"
                    />
                  </div>
                </div>

                {/* Grosor del marco */}
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-slate-700">Grosor</label>
                    <span className="text-xs text-slate-500">{contentFrameWidth} pt</span>
                  </div>
                  <input
                    type="range"
                    min={1}
                    max={8}
                    value={contentFrameWidth}
                    onChange={(e) => setContentFrameWidth(Number(e.target.value))}
                    className="w-full accent-slate-900"
                  />
                </div>

                {/* Separación del marco */}
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-slate-700">Separación del borde</label>
                    <span className="text-xs text-slate-500">{contentFramePadding.toFixed(1)} cm</span>
                  </div>
                  <p className="text-xs text-slate-400">Espacio entre la línea de corte y el marco.</p>
                  <input
                    type="range"
                    min={0}
                    max={1.5}
                    step={0.1}
                    value={contentFramePadding}
                    onChange={(e) => setContentFramePadding(Number(e.target.value))}
                    className="w-full accent-slate-900"
                  />
                </div>

                {/* Padding interno */}
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-slate-700">Padding interno</label>
                    <span className="text-xs text-slate-500">{contentInnerPadding.toFixed(1)} cm</span>
                  </div>
                  <p className="text-xs text-slate-400">Espacio entre el marco y el texto.</p>
                  <input
                    type="range"
                    min={0}
                    max={1.0}
                    step={0.1}
                    value={contentInnerPadding}
                    onChange={(e) => setContentInnerPadding(Number(e.target.value))}
                    className="w-full accent-slate-900"
                  />
                </div>
              </>
            )}
          </div>

          {/* ── E. Impresión ──────────────────────────────────────────────── */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
            <h3 className="text-sm font-semibold text-slate-900">Impresión</h3>

            <CardSizeSelector value={cardSize} onChange={setCardSize} />

            <PriceVisibilitySwitch checked={includePrice} onCheckedChange={setIncludePrice} />

            {/* Líneas de corte */}
            <div className="flex items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white px-3 py-2.5">
              <div>
                <p className="text-sm font-medium text-slate-800">Líneas de corte</p>
                <p className="text-xs text-slate-500">
                  Muestra guías punteadas alrededor de cada cartel
                </p>
              </div>
              <Switch checked={showCutLines} onCheckedChange={setShowCutLines} />
            </div>

            {/* Copias solo en modo producto */}
            {printableType === 'product' && (
              <div className="space-y-1.5">
                <label htmlFor="cartel-copies" className="text-sm font-medium text-slate-700">
                  Cantidad de copias
                </label>
                <input
                  id="cartel-copies"
                  type="number"
                  min={1}
                  max={MAX_COPIES_PER_ITEM}
                  value={copies}
                  onChange={(e) => setCopies(Number(e.target.value))}
                  className="w-24 rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900/20"
                />
                <p className="text-xs text-slate-400">
                  Podés generar hasta {MAX_COPIES_PER_ITEM} copias por cartel.
                </p>
                {copiesInvalid && (
                  <p className="text-xs text-red-600">
                    La cantidad debe estar entre 1 y {MAX_COPIES_PER_ITEM}.
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <GeneratePdfButton
            isLoading={isLoading}
            disabled={!canGenerate}
            onClick={handleGenerate}
          />

          {!canGenerate && (
            <p className="text-center text-xs text-slate-400">
              {printableType === 'promotion'
                ? 'Completá el título para generar el PDF.'
                : 'Seleccioná un producto o completá el título para generar el PDF.'}
            </p>
          )}
        </div>

        {/* ── Columna derecha: vista previa ──────────────────────────────── */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm flex flex-col items-center justify-center min-h-64">
          <PrintPreview
            title={previewTitle}
            price={previewPrice}
            oldPrice={previewOldPrice}
            promoText={previewPromoText}
            includePrice={includePrice}
            logoVariant={logoVariant}
            cardSize={cardSize}
            showCutLines={showCutLines}
            accentColor={branding?.accent_color ?? '#1e293b'}
            logoUrl={logoUrl ?? null}
            templateCode={selectedTemplate}
            layoutStyle={layoutStyle}
            fontPreset={fontPreset}
            logoSize={logoSize}
            titleFontSize={titleFontSize}
            priceFontSize={priceFontSize}
            secondaryFontSize={secondaryFontSize}
            contentFrameEnabled={contentFrameEnabled}
            contentFrameColor={contentFrameColor}
            contentFrameWidth={contentFrameWidth}
            contentFramePadding={contentFramePadding}
            contentInnerPadding={contentInnerPadding}
            textTransform={textTransform}
            headerContentType={headerContentType}
            headerText={headerText}
            headerTextColor={headerTextColor}
            titleTextColor={titleTextColor}
            priceTextColor={priceTextColor}
            priceGapPt={priceGapPt}
          />
        </div>
      </div>
    </div>
  );
}
