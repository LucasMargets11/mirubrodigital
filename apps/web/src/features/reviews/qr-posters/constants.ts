import type { OutlineWidth, PosterSize, PosterTemplateCode, TitleFont, QrScale, QrVerticalAlign, TextSpacing, UppercaseMode, PosterFontFamily, PosterFontWeight, PosterLogoVariant, PosterLogoPosition } from './types';
import type { GenerateQrPosterPayload } from './types';

export const POSTER_SIZES: Array<{
    code: PosterSize;
    label: string;
    description: string;
    aspectRatio: number;
    /** Ancho real del cartel en mm (para conversión px/mm en preview). */
    widthMm: number;
}> = [
    { code: 'a4_portrait',    label: 'A4 vertical',        description: '21 × 29.7 cm',  aspectRatio: 21 / 29.7,   widthMm: 210 },
    { code: 'a4_landscape',   label: 'A4 horizontal',      description: '29.7 × 21 cm',  aspectRatio: 29.7 / 21,   widthMm: 297 },
    { code: 'a5_portrait',    label: 'A5 vertical',        description: '14.8 × 21 cm',  aspectRatio: 14.8 / 21,   widthMm: 148 },
    { code: 'half_a4',        label: 'Media A4',           description: '21 × 14.85 cm', aspectRatio: 21 / 14.85,  widthMm: 210 },
    { code: 'desk_card',      label: 'Tarjeta mostrador',  description: '15 × 10 cm',    aspectRatio: 15 / 10,     widthMm: 150 },
    { code: 'sticker_square', label: 'Sticker cuadrado',   description: '10 × 10 cm',    aspectRatio: 1,           widthMm: 100 },
];

export const POSTER_TEMPLATES: Array<{
    code: PosterTemplateCode;
    label: string;
    description: string;
}> = [
    {
        code: 'simple_centered',
        label: 'Clásico centrado',
        description: 'Logo, texto y QR centrados verticalmente',
    },
    {
        code: 'qr_left',
        label: 'QR lateral',
        description: 'QR a la izquierda, texto a la derecha',
    },
    {
        code: 'bold_cta',
        label: 'Llamado destacado',
        description: 'Texto grande, QR en caja blanca',
    },
];

export const BACKGROUND_COLORS: Array<{ hex: string; name: string }> = [
    { hex: '#FFFFFF', name: 'Blanco' },
    { hex: '#F8FAFC', name: 'Gris claro' },
    { hex: '#FEF3C7', name: 'Amarillo suave' },
    { hex: '#DCFCE7', name: 'Verde suave' },
    { hex: '#DBEAFE', name: 'Azul suave' },
    { hex: '#111827', name: 'Negro' },
];

export const DEFAULT_MAIN_TEXT = 'Escaneá y dejanos tu opinión';
export const DEFAULT_SUBTITLE = 'Tu reseña nos ayuda a mejorar';
export const DEFAULT_BACKGROUND = '#FFFFFF';

export const TITLE_FONT_OPTIONS: Array<{
    value: TitleFont;
    label: string;
    previewClass: string;
}> = [
    { value: 'sans_bold',  label: 'Sans moderna',    previewClass: 'font-sans font-bold' },
    { value: 'serif_bold', label: 'Serif elegante',   previewClass: 'font-serif font-bold' },
    { value: 'mono_bold',  label: 'Mono fuerte',      previewClass: 'font-mono font-bold' },
];

// ── Sistema avanzado de tipografías ──────────────────────────────────────────

export interface PosterFontWeightEntry {
    id: PosterFontWeight;
    label: string;
    /** Valor numérico CSS fontWeight. */
    cssWeight: 400 | 700 | 900;
}

export interface PosterFontFamilyEntry {
    id: PosterFontFamily;
    label: string;
    category: string;
    /** Valor para fontFamily CSS (Google Fonts name). */
    cssFamily: string;
    recommendedFor: string;
    weights: PosterFontWeightEntry[];
}

export const POSTER_FONT_FAMILIES: PosterFontFamilyEntry[] = [
    {
        id: 'cinzel',
        label: 'Cinzel',
        category: 'Elegante',
        cssFamily: "'Cinzel', serif",
        recommendedFor: 'Premium, restaurantes, hoteles, estética clásica',
        weights: [
            { id: 'regular', label: 'Regular', cssWeight: 400 },
            { id: 'bold',    label: 'Bold',    cssWeight: 700 },
            { id: 'black',   label: 'Black',   cssWeight: 900 },
        ],
    },
    {
        id: 'montserrat',
        label: 'Montserrat',
        category: 'Moderna',
        cssFamily: "'Montserrat', sans-serif",
        recommendedFor: 'Comercial, versátil, moderna',
        weights: [
            { id: 'regular', label: 'Regular', cssWeight: 400 },
            { id: 'bold',    label: 'Bold',    cssWeight: 700 },
            { id: 'black',   label: 'Black',   cssWeight: 900 },
        ],
    },
    {
        id: 'poppins',
        label: 'Poppins',
        category: 'Moderna',
        cssFamily: "'Poppins', sans-serif",
        recommendedFor: 'Geométrica, friendly, moderna',
        weights: [
            { id: 'regular', label: 'Regular', cssWeight: 400 },
            { id: 'bold',    label: 'Bold',    cssWeight: 700 },
            { id: 'black',   label: 'Black',   cssWeight: 900 },
        ],
    },
    {
        id: 'raleway',
        label: 'Raleway',
        category: 'Elegante',
        cssFamily: "'Raleway', sans-serif",
        recommendedFor: 'Elegante, minimalista, moda',
        weights: [
            { id: 'regular', label: 'Regular', cssWeight: 400 },
            { id: 'bold',    label: 'Bold',    cssWeight: 700 },
            { id: 'black',   label: 'Black',   cssWeight: 900 },
        ],
    },
    {
        id: 'playfair_display',
        label: 'Playfair Display',
        category: 'Premium',
        cssFamily: "'Playfair Display', serif",
        recommendedFor: 'Editorial, sofisticada, títulos premium',
        weights: [
            { id: 'regular', label: 'Regular', cssWeight: 400 },
            { id: 'bold',    label: 'Bold',    cssWeight: 700 },
            { id: 'black',   label: 'Black',   cssWeight: 900 },
        ],
    },
    {
        id: 'work_sans',
        label: 'Work Sans',
        category: 'Comercial',
        cssFamily: "'Work Sans', sans-serif",
        recommendedFor: 'Profesional, clara, cartelería comercial',
        weights: [
            { id: 'regular', label: 'Regular', cssWeight: 400 },
            { id: 'bold',    label: 'Bold',    cssWeight: 700 },
            { id: 'black',   label: 'Black',   cssWeight: 900 },
        ],
    },
    {
        id: 'lato',
        label: 'Lato',
        category: 'Moderna',
        cssFamily: "'Lato', sans-serif",
        recommendedFor: 'Clara, cálida, institucional',
        weights: [
            { id: 'regular', label: 'Regular', cssWeight: 400 },
            { id: 'bold',    label: 'Bold',    cssWeight: 700 },
            { id: 'black',   label: 'Black',   cssWeight: 900 },
        ],
    },
    {
        id: 'oswald',
        label: 'Oswald',
        category: 'Condensada',
        cssFamily: "'Oswald', sans-serif",
        recommendedFor: 'Condensada, fuerte, promociones, titulares',
        weights: [
            { id: 'regular', label: 'Regular', cssWeight: 400 },
            { id: 'bold',    label: 'Bold',    cssWeight: 700 },
        ],
    },
    {
        id: 'cormorant_garamond',
        label: 'Cormorant Garamond',
        category: 'Premium',
        cssFamily: "'Cormorant Garamond', serif",
        recommendedFor: 'Boutique, premium, gastronómico elegante',
        weights: [
            { id: 'regular', label: 'Regular', cssWeight: 400 },
            { id: 'bold',    label: 'Bold',    cssWeight: 700 },
        ],
    },
    {
        id: 'libre_baskerville',
        label: 'Libre Baskerville',
        category: 'Clásica',
        cssFamily: "'Libre Baskerville', serif",
        recommendedFor: 'Clásica, seria, sobria',
        weights: [
            { id: 'regular', label: 'Regular', cssWeight: 400 },
            { id: 'bold',    label: 'Bold',    cssWeight: 700 },
        ],
    },
];

/** Devuelve la entrada de familia para un id dado, o undefined si no existe. */
export function getPosterFontFamily(id: PosterFontFamily | null | undefined): PosterFontFamilyEntry | undefined {
    if (!id) return undefined;
    return POSTER_FONT_FAMILIES.find((f) => f.id === id);
}

/**
 * Resuelve el peso a usar para una familia dada.
 * Si el peso solicitado no existe para esa familia, cae a 'bold' o al último disponible.
 */
export function resolvePosterFontWeight(
    family: PosterFontFamilyEntry,
    requestedWeight: PosterFontWeight | null | undefined,
): PosterFontWeightEntry {
    const weight = requestedWeight ?? 'bold';
    const found = family.weights.find((w) => w.id === weight);
    if (found) return found;
    // Fallback: bold > regular > primer disponible
    return (
        family.weights.find((w) => w.id === 'bold') ??
        family.weights.find((w) => w.id === 'regular') ??
        family.weights[0]
    );
}

export const TEXT_COLOR_PALETTE: Array<{ hex: string; name: string }> = [
    { hex: '#FFFFFF', name: 'Blanco' },
    { hex: '#111827', name: 'Negro' },
    { hex: '#FACC15', name: 'Amarillo' },
    { hex: '#F97316', name: 'Naranja' },
    { hex: '#22C55E', name: 'Verde' },
    { hex: '#3B82F6', name: 'Azul' },
    { hex: '#EC4899', name: 'Rosa' },
];

export const OUTLINE_COLOR_PALETTE: Array<{ hex: string; name: string }> = [
    { hex: '#000000', name: 'Negro' },
    { hex: '#FFFFFF', name: 'Blanco' },
    { hex: '#111827', name: 'Gris oscuro' },
    { hex: '#FACC15', name: 'Amarillo' },
    { hex: '#3B82F6', name: 'Azul' },
];

export const OUTLINE_WIDTH_OPTIONS: Array<{ value: OutlineWidth; label: string }> = [
    { value: 0.25, label: 'Fino' },
    { value: 0.4,  label: 'Medio' },
    { value: 0.6,  label: 'Grueso' },
    { value: 0.8,  label: 'Muy grueso' },
];

export const QR_SCALE_OPTIONS: Array<{ value: QrScale; label: string }> = [
    { value: 'small',  label: 'Chico' },
    { value: 'medium', label: 'Mediano' },
    { value: 'large',  label: 'Grande' },
];

export const TEXT_SPACING_OPTIONS: Array<{ value: TextSpacing; label: string }> = [
    { value: 'tight',  label: 'Compacta' },
    { value: 'normal', label: 'Normal' },
    { value: 'loose',  label: 'Amplia' },
];

export const UPPERCASE_OPTIONS: Array<{ value: UppercaseMode; label: string }> = [
    { value: 'none',  label: 'Normal' },
    { value: 'title', label: 'Título' },
    { value: 'all',   label: 'Todo' },
];

// ── Nuevos controles de posición y tamaño del QR ──────────────────────────────

export const QR_VERTICAL_ALIGN_OPTIONS: Array<{ value: QrVerticalAlign; label: string }> = [
    { value: 'top',    label: 'Arriba' },
    { value: 'center', label: 'Centro' },
    { value: 'bottom', label: 'Abajo' },
];

export const QR_SIZE_MM_PRESETS: Array<{ label: string; value: number }> = [
    { label: 'Chico',   value: 32 },
    { label: 'Mediano', value: 48 },
    { label: 'Grande',  value: 68 },
];

export const QR_SIZE_MM_MIN = 22;
export const QR_SIZE_MM_MAX = 90;
export const QR_BOTTOM_OFFSET_MM_MIN = 0;
export const QR_BOTTOM_OFFSET_MM_MAX = 80;
export const QR_BOTTOM_OFFSET_MM_DEFAULT = 16;

/**
 * Mapa de qr_scale legacy a mm reales.
 * Usado para backward compat: diseños sin qr_size_mm usan este valor.
 */
export const QR_SCALE_TO_MM: Record<string, number> = {
    small:  32,
    medium: 48,
    large:  68,
};

/**
 * Resuelve el tamaño real del QR en mm desde el payload.
 * Si el payload tiene qr_size_mm, lo usa directamente.
 * Si no, deriva del qr_scale legacy (backward compat).
 */
export function resolveQrSizeMm(payload: Pick<GenerateQrPosterPayload, 'qr_size_mm' | 'qr_scale'>): number {
    if (payload.qr_size_mm != null) return payload.qr_size_mm;
    return QR_SCALE_TO_MM[payload.qr_scale ?? 'medium'] ?? 48;
}

// ── Logo del negocio ──────────────────────────────────────────────────────────

export const LOGO_VARIANT_OPTIONS: Array<{ value: PosterLogoVariant; label: string }> = [
    { value: 'none',       label: 'Sin logo' },
    { value: 'horizontal', label: 'Horizontal' },
    { value: 'square',     label: 'Cuadrado' },
];

export const LOGO_POSITION_OPTIONS: Array<{ value: PosterLogoPosition; label: string }> = [
    { value: 'top-left',      label: 'Arriba izq.' },
    { value: 'top-center',    label: 'Arriba centro' },
    { value: 'top-right',     label: 'Arriba der.' },
    { value: 'bottom-left',   label: 'Abajo izq.' },
    { value: 'bottom-center', label: 'Abajo centro' },
    { value: 'bottom-right',  label: 'Abajo der.' },
    { value: 'middle-left',   label: 'Lateral izq.' },
    { value: 'middle-right',  label: 'Lateral der.' },
];

export const LOGO_MARGIN_MM_MIN = 0;
export const LOGO_MARGIN_MM_MAX = 40;
export const LOGO_MARGIN_MM_DEFAULT = 8;
