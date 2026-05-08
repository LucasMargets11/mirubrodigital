import type {
  PrintableCardSize,
  LogoVariant,
  PrintableTemplateCode,
  PrintableType,
  LayoutStyle,
  FontPreset,
  BorderStyle,
  LogoSize,
  FontSizeOption,
  TextTransform,
  HeaderContentType,
} from './types';

export const PRINTABLE_CARD_SIZES: readonly PrintableCardSize[] = [
  { code: '5x3',  label: '5 × 3 cm',     widthCm: 5,    heightCm: 3    },
  { code: '6x4',  label: '6 × 4 cm',     widthCm: 6,    heightCm: 4    },
  { code: '7x5',  label: '7 × 5 cm',     widthCm: 7,    heightCm: 5    },
  { code: '10x7', label: '10 × 7 cm',    widthCm: 10,   heightCm: 7    },
  { code: '12x8', label: '12 × 8 cm',    widthCm: 12,   heightCm: 8    },
  { code: '15x10',label: '15 × 10 cm',   widthCm: 15,   heightCm: 10   },
  { code: 'a6',   label: 'A6',           widthCm: 10.5, heightCm: 14.8 },
  { code: 'a5',   label: 'A5',           widthCm: 14.8, heightCm: 21   },
  { code: 'a4',   label: 'A4 completo',  widthCm: 21,   heightCm: 29.7 },
] as const;

export const DEFAULT_CARD_SIZE = PRINTABLE_CARD_SIZES[3]; // 10x7

/** Máximo de copias por ítem aceptado por el backend. */
export const MAX_COPIES_PER_ITEM = 20;

export const PRINTABLE_TEMPLATES: readonly {
  code: PrintableTemplateCode;
  type: PrintableType;
  label: string;
}[] = [
  { code: 'product_price_simple', type: 'product',   label: 'Producto simple'  },
  { code: 'promo_offer',          type: 'promotion',  label: 'Oferta'           },
  { code: 'promo_discount',       type: 'promotion',  label: 'Descuento %'      },
  { code: 'promo_2x1',            type: 'promotion',  label: '2x1'              },
  { code: 'promo_combo',          type: 'promotion',  label: 'Combo'            },
  { code: 'promo_clearance',      type: 'promotion',  label: 'Liquidación'      },
  { code: 'promo_weekly',         type: 'promotion',  label: 'Promo semanal'    },
] as const;

export const LOGO_VARIANT_OPTIONS: readonly { value: LogoVariant; label: string }[] = [
  { value: 'none',       label: 'Sin logo'              },
  { value: 'horizontal', label: 'Logo horizontal'       },
  { value: 'square',     label: 'Logo cuadrado'         },
  { value: 'default',    label: 'Logo predeterminado'   },
] as const;

// ── Phase 4: opciones de diseño visual ───────────────────────────────────────

export const LAYOUT_STYLE_OPTIONS: readonly { value: LayoutStyle; label: string }[] = [
  { value: 'centered_product', label: 'Clásico centrado'   },
  { value: 'price_focus',      label: 'Foco en precio'     },
  { value: 'promo_badge',      label: 'Badge de promo'     },
  { value: 'framed_label',     label: 'Etiqueta enmarcada' },
  { value: 'minimal_label',    label: 'Etiqueta mínima'    },
] as const;

export const FONT_PRESET_OPTIONS: readonly { value: FontPreset; label: string }[] = [
  { value: 'bold',      label: 'Negrita'   },
  { value: 'regular',   label: 'Regular'   },
  { value: 'elegant',   label: 'Elegante'  },
  { value: 'condensed', label: 'Compacta'  },
] as const;

export const BORDER_STYLE_OPTIONS: readonly { value: BorderStyle; label: string }[] = [
  { value: 'none',   label: 'Sin borde'       },
  { value: 'black',  label: 'Negro'           },
  { value: 'accent', label: 'Acento'          },
  { value: 'custom', label: 'Personalizado'   },
] as const;

export const LOGO_SIZE_OPTIONS: readonly { value: LogoSize; label: string }[] = [
  { value: 'small',  label: 'Pequeño'     },
  { value: 'medium', label: 'Mediano'     },
  { value: 'large',  label: 'Grande'      },
  { value: 'xlarge', label: 'Muy grande'  },
] as const;

// ── Phase 5: opciones de tamaño de fuente ──────────────────────────────────

export const FONT_SIZE_OPTIONS: readonly { value: FontSizeOption; label: string }[] = [
  { value: 'small',  label: 'Pequeño'     },
  { value: 'medium', label: 'Mediano'     },
  { value: 'large',  label: 'Grande'      },
  { value: 'xlarge', label: 'Muy grande'  },
] as const;

// ── Phase 7: transformación de texto ─────────────────────────────────────────

export const TEXT_TRANSFORM_OPTIONS: readonly { value: TextTransform; label: string }[] = [
  { value: 'none',      label: 'Normal'     },
  { value: 'uppercase', label: 'MAYÚSCULAS' },
] as const;

// ── Phase 8: zona superior ────────────────────────────────────────────────────

export const HEADER_CONTENT_OPTIONS: readonly { value: HeaderContentType; label: string }[] = [
  { value: 'highlight_text', label: 'Texto destacado' },
  { value: 'logo',           label: 'Logo'            },
  { value: 'none',           label: 'Nada'            },
] as const;

// ── Phase 9: colores de texto y espaciado ────────────────────────────────────

export const DEFAULT_HEADER_TEXT_COLOR = '#DC2626';
export const DEFAULT_TITLE_TEXT_COLOR  = '#111827';
export const DEFAULT_PRICE_TEXT_COLOR  = '#000000';
export const DEFAULT_PRICE_GAP_PT      = 10;

export const TEXT_COLOR_OPTIONS: readonly { value: string; label: string }[] = [
  { value: '#111827', label: 'Negro' },
  { value: '#DC2626', label: 'Rojo'  },
  { value: '#2563EB', label: 'Azul'  },
  { value: '#16A34A', label: 'Verde' },
  { value: '#6B7280', label: 'Gris'  },
] as const;
