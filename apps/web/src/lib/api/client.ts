const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export class ApiError extends Error {
    status: number;
    payload?: unknown;

    constructor(message: string, status: number, payload?: unknown) {
        super(message);
        this.status = status;
        this.payload = payload;
    }
}

async function parseResponse(response: Response) {
    const contentType = response.headers.get('content-type') ?? '';
    if (contentType.includes('application/json')) {
        return response.json().catch(() => undefined);
    }
    return undefined;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
    const bodyIsFormData = typeof FormData !== 'undefined' && init?.body instanceof FormData;
    const response = await fetch(`${API_URL}${path}`, {
        credentials: 'include',
        headers: {
            ...(bodyIsFormData ? {} : { 'Content-Type': 'application/json' }),
            ...(init?.headers ?? {}),
        },
        ...init,
    });

    if (!response.ok) {
        const payload = await parseResponse(response);
        const detail = (payload as { detail?: string } | undefined)?.detail;
        throw new ApiError(detail ?? 'Error inesperado en la API', response.status, payload);
    }

    if (response.status === 204) {
        return undefined as T;
    }

    return (await response.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
    return apiFetch<T>(path, { method: 'GET' });
}

export async function apiGetBlob(path: string): Promise<Blob> {
    const response = await fetch(`${API_URL}${path}`, {
        method: 'GET',
        credentials: 'include',
    });

    if (!response.ok) {
        const payload = await parseResponse(response);
        const detail = (payload as { detail?: string } | undefined)?.detail;
        throw new ApiError(detail ?? 'Error inesperado en la API', response.status, payload);
    }

    return response.blob();
}

function resolveBody(body?: unknown): BodyInit | undefined {
    if (body instanceof FormData) {
        return body;
    }
    if (body === undefined || body === null) {
        return undefined;
    }
    return JSON.stringify(body);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
    return apiFetch<T>(path, {
        method: 'POST',
        body: resolveBody(body),
    });
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> {
    return apiFetch<T>(path, {
        method: 'PATCH',
        body: resolveBody(body),
    });
}

export function apiPut<T>(path: string, body?: unknown): Promise<T> {
    return apiFetch<T>(path, {
        method: 'PUT',
        body: resolveBody(body),
    });
}

export function apiDelete<T>(path: string): Promise<T> {
    return apiFetch<T>(path, { method: 'DELETE' });
}
