/**
 * API para generación de Carteles QR de Reseñas PRO.
 *
 * Reutiliza downloadBlob de printables/api.ts — no se duplica el helper.
 */
import { downloadBlob } from '@/features/printables/api';
import type { GenerateQrPosterPayload } from './types';

export { downloadBlob };

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

/**
 * Llama a POST /api/v1/reviews/qr-posters/generate-pdf/ y devuelve el Blob del PDF.
 * Lanza Error con mensaje localizado según el código HTTP de error.
 */
export async function generateQrPosterPdf(payload: GenerateQrPosterPayload): Promise<Blob> {
    const { background_image, ...fields } = payload;
    const useFormData = fields.background_mode === 'image' && background_image instanceof File;

    let body: BodyInit;
    const extraHeaders: Record<string, string> = {};

    if (useFormData && background_image instanceof File) {
        const fd = new FormData();
        fd.append('poster_size', fields.poster_size);
        fd.append('template_code', fields.template_code);
        fd.append('main_text', fields.main_text);
        if (fields.subtitle != null) fd.append('subtitle', fields.subtitle);
        fd.append('include_logo', String(fields.include_logo));
        fd.append('logo_variant', fields.logo_variant);
        fd.append('background_color', fields.background_color);
        fd.append('background_mode', 'image');
        fd.append('background_image', background_image);
        fd.append('title_font', fields.title_font ?? 'sans_bold');
        if (fields.font_family != null) fd.append('font_family', fields.font_family);
        if (fields.font_weight != null) fd.append('font_weight', fields.font_weight);
        if (fields.main_text_color) fd.append('main_text_color', fields.main_text_color);
        if (fields.subtitle_text_color) fd.append('subtitle_text_color', fields.subtitle_text_color);
        fd.append('main_text_outline_enabled', String(fields.main_text_outline_enabled));
        fd.append('main_text_outline_color', fields.main_text_outline_color);
        fd.append('subtitle_text_outline_enabled', String(fields.subtitle_text_outline_enabled));
        fd.append('subtitle_text_outline_color', fields.subtitle_text_outline_color);
        fd.append('text_outline_width', String(fields.text_outline_width));
        fd.append('qr_scale', fields.qr_scale ?? 'medium');
        if (fields.qr_vertical_align != null) fd.append('qr_vertical_align', fields.qr_vertical_align);
        if (fields.qr_size_mm != null) fd.append('qr_size_mm', String(fields.qr_size_mm));
        if (fields.qr_bottom_offset_mm != null) fd.append('qr_bottom_offset_mm', String(fields.qr_bottom_offset_mm));
        fd.append('text_spacing', fields.text_spacing ?? 'normal');
        fd.append('uppercase_mode', fields.uppercase_mode ?? 'none');
        body = fd;
        // Do NOT set Content-Type — browser adds multipart/form-data boundary automatically
    } else {
        extraHeaders['Content-Type'] = 'application/json';
        body = JSON.stringify(fields);
    }

    const response = await fetch(`${API_URL}/api/v1/reviews/qr-posters/generate-pdf/`, {
        method: 'POST',
        credentials: 'include',
        headers: extraHeaders,
        body,
    });

    if (!response.ok) {
        if (response.status === 403) {
            throw new Error('Esta función está disponible en Reseñas PRO.');
        }
        let message = 'No pudimos generar el cartel. Intentá nuevamente.';
        try {
            const data = await response.json() as { message?: string; detail?: string };
            message = data?.message ?? data?.detail ?? message;
        } catch {
            // mantener mensaje default
        }
        throw new Error(message);
    }

    return response.blob();
}
