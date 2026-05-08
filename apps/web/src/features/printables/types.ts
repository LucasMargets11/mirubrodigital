export type PrintableType = 'product' | 'promotion';

export type PrintableTemplateCode =
  | 'product_price_simple'
  | 'promo_offer'
  | 'promo_discount'
  | 'promo_2x1'
  | 'promo_combo'
  | 'promo_clearance'
  | 'promo_weekly';

/** Plantilla por defecto para cada tipo. Puede ser sobreescrita por el usuario. */
export const DEFAULT_TEMPLATE_FOR_TYPE: Record<PrintableType, PrintableTemplateCode> = {
  product:   'product_price_simple',
  promotion: 'promo_offer',
};

export type PaperSize = 'A4';

export type LogoVariant = 'none' | 'horizontal' | 'square' | 'default';

// ── Phase 4: Diseño visual ────────────────────────────────────────────────────

export type LayoutStyle =
  | 'centered_product'
  | 'price_focus'
  | 'promo_badge'
  | 'framed_label'
  | 'minimal_label';

export type FontPreset = 'bold' | 'regular' | 'elegant' | 'condensed';

export type BorderStyle = 'none' | 'black' | 'accent' | 'custom';

export type LogoSize = 'small' | 'medium' | 'large' | 'xlarge';

export type FontSizeOption = 'small' | 'medium' | 'large' | 'xlarge';

// Phase 7: transformación de texto
export type TextTransform = 'none' | 'uppercase';

// Phase 8: zona superior configurable
export type HeaderContentType = 'logo' | 'highlight_text' | 'none';

export type LogoPosition = 'top_center' | 'top_left';

export type PrintableCardSize = {
  code: string;
  label: string;
  widthCm: number;
  heightCm: number;
};

export type PrintableItem = {
  product_id?: string | null;
  title: string;
  description?: string;
  price?: string;
  old_price?: string;
  promo_text?: string;
  copies: number;
};

export type GeneratePrintablePdfPayload = {
  type: PrintableType;
  template_code: PrintableTemplateCode;
  paper_size: PaperSize;
  card_size: {
    width_cm: number;
    height_cm: number;
  };
  logo_variant: LogoVariant;
  include_logo: boolean;
  include_price: boolean;
  show_cut_lines: boolean;
  items: PrintableItem[];
  // Phase 4: opciones de diseño visual (opcionales, el backend usa defaults)
  layout_style?: LayoutStyle;
  font_preset?: FontPreset;
  border_style?: BorderStyle;
  border_color?: string;
  border_width?: number;
  border_radius?: number;
  logo_size?: LogoSize;
  logo_position?: LogoPosition;
  // Phase 5: tipografía
  inner_border_padding_cm?: number;
  title_font_size?: FontSizeOption;
  price_font_size?: FontSizeOption;
  secondary_font_size?: FontSizeOption;
  // Phase 6: marco de contenido
  content_frame_enabled?: boolean;
  content_frame_color?: string;
  content_frame_width?: number;
  content_frame_padding_cm?: number;
  content_inner_padding_cm?: number;
  // Phase 7: transformación de texto
  text_transform?: TextTransform;
  // Phase 8: zona superior configurable
  header_content_type?: HeaderContentType;
  header_text?: string;
  // Phase 9: colores y espaciado
  header_text_color?: string;
  title_text_color?: string;
  price_text_color?: string;
  price_gap_pt?: number;
};
