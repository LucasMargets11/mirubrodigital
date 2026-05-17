/**
 * API client para el historial de diseños de Carteles QR de Reseñas PRO.
 *
 * Endpoints:
 *   GET    /api/v1/reviews/qr-posters/designs/
 *   POST   /api/v1/reviews/qr-posters/designs/
 *   PATCH  /api/v1/reviews/qr-posters/designs/<uuid>/
 *   DELETE /api/v1/reviews/qr-posters/designs/<uuid>/
 */
import type {
    QrPosterDesign,
    QrPosterDesignListResponse,
    SaveDesignInput,
    UpdateDesignInput,
} from './designs-types';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const BASE = `${API_URL}/api/v1/reviews/qr-posters/designs/`;

async function handleResponse<T>(res: Response): Promise<T> {
    if (res.ok) {
        if (res.status === 204) return undefined as T;
        return res.json() as Promise<T>;
    }
    let data: { code?: string; message?: string; detail?: string } = {};
    try {
        data = (await res.json()) as typeof data;
    } catch {
        // ignore parse errors
    }
    const err = new Error(
        data.message ?? data.detail ?? 'Error inesperado. Intentá nuevamente.',
    ) as Error & { code?: string };
    err.code = data.code;
    throw err;
}

export async function listQrPosterDesigns(): Promise<QrPosterDesignListResponse> {
    const res = await fetch(BASE, { credentials: 'include' });
    return handleResponse<QrPosterDesignListResponse>(res);
}

export async function createQrPosterDesign(input: SaveDesignInput): Promise<QrPosterDesign> {
    const useFormData =
        input.payload.background_mode === 'image' && input.background_image instanceof File;

    let body: BodyInit;
    const headers: Record<string, string> = {};

    if (useFormData && input.background_image instanceof File) {
        const fd = new FormData();
        fd.append('name', input.name);
        fd.append('payload', JSON.stringify(input.payload));
        fd.append('background_image', input.background_image);
        body = fd;
        // Do NOT set Content-Type — browser sets multipart/form-data with boundary
    } else {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify({ name: input.name, payload: input.payload });
    }

    const res = await fetch(BASE, {
        method: 'POST',
        credentials: 'include',
        headers,
        body,
    });
    return handleResponse<QrPosterDesign>(res);
}

export async function updateQrPosterDesign(
    id: string,
    input: UpdateDesignInput,
): Promise<QrPosterDesign> {
    const useFormData =
        input.payload?.background_mode === 'image' && input.background_image instanceof File;

    let body: BodyInit;
    const headers: Record<string, string> = {};

    if (useFormData && input.background_image instanceof File) {
        const fd = new FormData();
        if (input.name !== undefined) fd.append('name', input.name);
        if (input.payload !== undefined) fd.append('payload', JSON.stringify(input.payload));
        fd.append('background_image', input.background_image);
        body = fd;
    } else {
        headers['Content-Type'] = 'application/json';
        const bodyObj: Record<string, unknown> = {};
        if (input.name !== undefined) bodyObj.name = input.name;
        if (input.payload !== undefined) bodyObj.payload = input.payload;
        body = JSON.stringify(bodyObj);
    }

    const res = await fetch(`${BASE}${id}/`, {
        method: 'PATCH',
        credentials: 'include',
        headers,
        body,
    });
    return handleResponse<QrPosterDesign>(res);
}

export async function deleteQrPosterDesign(id: string): Promise<void> {
    const res = await fetch(`${BASE}${id}/`, {
        method: 'DELETE',
        credentials: 'include',
    });
    return handleResponse<void>(res);
}

/**
 * Genera y descarga el PDF del cartel desde un diseño guardado con imagen.
 * Lanza un Error con `code` si la API responde con error.
 */
export async function generatePdfFromDesign(id: string): Promise<void> {
    const res = await fetch(`${BASE}${id}/generate-pdf/`, {
        method: 'POST',
        credentials: 'include',
    });
    if (!res.ok) {
        let data: { code?: string; detail?: string } = {};
        try {
            data = (await res.json()) as typeof data;
        } catch {
            // ignore
        }
        const err = new Error(data.detail ?? 'Error generando PDF.') as Error & { code?: string };
        err.code = data.code;
        throw err;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'cartel-qr-resenas.pdf';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}
