import { cookies } from 'next/headers';

const PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const INTERNAL_API_URL = process.env.API_INTERNAL_URL ?? process.env.INTERNAL_API_URL ?? PUBLIC_API_URL;
const API_URL = INTERNAL_API_URL;

async function buildCookieHeader(): Promise<string | undefined> {
    const store = await cookies();
    const serialized = store
        .getAll()
        .map((cookie) => `${cookie.name}=${cookie.value}`)
        .join('; ');
    return serialized.length ? serialized : undefined;
}

async function parseBody(response: Response) {
    const contentType = response.headers.get('content-type') ?? '';
    if (contentType.includes('application/json')) {
        return response.json().catch(() => undefined);
    }
    return undefined;
}

export async function serverApiFetch<T>(path: string, init?: RequestInit): Promise<T> {
    const cookieHeader = await buildCookieHeader();
    const response = await fetch(`${API_URL}${path}`, {
        method: 'GET',
        cache: 'no-store',
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
            ...(cookieHeader ? { Cookie: cookieHeader } : {}),
            ...(init?.headers ?? {}),
        },
        ...init,
    });

    if (!response.ok) {
        const payload = await parseBody(response);
        const detail = (payload as { detail?: string } | undefined)?.detail;
        throw new Error(detail ?? `API request failed with status ${response.status}`);
    }

    if (response.status === 204) {
        return undefined as T;
    }

    return (await response.json()) as T;
}
