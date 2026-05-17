export type TitleFont = 'sans_bold' | 'serif_bold' | 'mono_bold';

// ── Nueva tipografía avanzada ──────────────────────────────────────────────────
export type PosterFontFamily =
    | 'cinzel'
    | 'montserrat'
    | 'poppins'
    | 'raleway'
    | 'playfair_display'
    | 'work_sans'
    | 'lato'
    | 'oswald'
    | 'cormorant_garamond'
    | 'libre_baskerville';

export type PosterFontWeight = 'regular' | 'bold' | 'black';

export type OutlineWidth = 0.25 | 0.4 | 0.6 | 0.8;

export type PosterSize =
    | 'a4_portrait'
    | 'a4_landscape'
    | 'a5_portrait'
    | 'half_a4'
    | 'desk_card'
    | 'sticker_square';

export type PosterTemplateCode = 'simple_centered' | 'qr_left' | 'bold_cta';

export type PosterLogoVariant = 'default' | 'horizontal' | 'square' | 'none';

export type PosterLogoPosition =
    | 'top-left'
    | 'top-center'
    | 'top-right'
    | 'bottom-left'
    | 'bottom-center'
    | 'bottom-right'
    | 'middle-left'
    | 'middle-right';

export type BackgroundMode = 'color' | 'image';

export type QrScale = 'small' | 'medium' | 'large';
export type QrVerticalAlign = 'top' | 'center' | 'bottom';
export type TextSpacing = 'tight' | 'normal' | 'loose';
export type UppercaseMode = 'none' | 'title' | 'all';

export interface GenerateQrPosterPayload {
    poster_size: PosterSize;
    template_code: PosterTemplateCode;
    main_text: string;
    subtitle?: string;
    include_logo: boolean;
    logo_variant: PosterLogoVariant;
    logo_position?: PosterLogoPosition;
    /** Distance from the poster border in mm (0–40). Default: 8. */
    logo_margin_mm?: number;
    background_color: string;
    background_mode: BackgroundMode;
    background_image?: File | null;
    /** @deprecated Usar font_family + font_weight. Mantenido por backward compat. */
    title_font: TitleFont;
    font_family?: PosterFontFamily | null;
    font_weight?: PosterFontWeight | null;
    main_text_color?: string | null;
    subtitle_text_color?: string | null;
    main_text_outline_enabled: boolean;
    main_text_outline_color: string;
    subtitle_text_outline_enabled: boolean;
    subtitle_text_outline_color: string;
    text_outline_width: OutlineWidth;
    qr_scale?: QrScale;
    qr_vertical_align?: QrVerticalAlign;
    qr_size_mm?: number | null;
    qr_bottom_offset_mm?: number | null;
    text_spacing?: TextSpacing;
    uppercase_mode?: UppercaseMode;
}
