/**
 * Returns the internal/server-side API base URL.
 * Used for SSR fetch calls inside Docker Compose (api:8000) or local dev.
 * NEVER expose this URL to the browser.
 */
export function getServerApiBaseUrl(): string {
    // 1. Docker/Internal Network (SSR)
    if (process.env.API_URL_INTERNAL) {
        return process.env.API_URL_INTERNAL;
    }
    // 2. Generic API URL (Manual override)
    if (process.env.API_URL) {
        return process.env.API_URL;
    }
    // 3. Client URL fallback (only works for SSR if localhost:8000 is accessible, e.g. local dev)
    if (process.env.NEXT_PUBLIC_API_URL) {
        return process.env.NEXT_PUBLIC_API_URL;
    }
    // 4. Default fallback
    return 'http://localhost:8000';
}

/**
 * Returns the public-facing API base URL the browser can reach.
 * Dev: http://localhost:8000  |  Prod: https://api.yourdomain.com
 */
export function getPublicApiBaseUrl(): string {
    return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
}

/** @deprecated Use getPublicApiBaseUrl() instead */
export function getClientApiBaseUrl(): string {
    return getPublicApiBaseUrl();
}

/**
 * Rewrites any media URL so the browser can always reach it.
 *
 * Rules:
 *  - Relative path  → prepend public API base
 *  - Absolute URL with internal host (api:8000, INTERNAL_API_URL) → replace with public base
 *  - Already-public absolute URL → returned unchanged
 *  - null/undefined → null
 *
 * Safe to call on both server (SSR) and client.
 */
export function buildMediaUrl(pathOrUrl: string | null | undefined): string | null {
    if (!pathOrUrl) return null;

    const publicBase = getPublicApiBaseUrl().replace(/\/$/, '');
    const internalBase = getServerApiBaseUrl().replace(/\/$/, '');

    // Relative path – prepend the public base
    if (!pathOrUrl.startsWith('http')) {
        return `${publicBase}/${pathOrUrl.replace(/^\//, '')}`;
    }

    // Replace known internal base when it differs from the public one
    if (internalBase !== publicBase && pathOrUrl.startsWith(internalBase)) {
        return publicBase + pathOrUrl.slice(internalBase.length);
    }

    // Catch the literal docker-compose service hostname regardless of env config
    // (backend may hardcode it in serialised URLs)
    for (const pattern of ['http://api:8000', 'https://api:8000']) {
        if (pathOrUrl.startsWith(pattern)) {
            if (process.env.NODE_ENV === 'development') {
                console.warn(
                    `[buildMediaUrl] Rewrote internal URL: ${pathOrUrl} → ${publicBase + pathOrUrl.slice(pattern.length)}`
                );
            }
            return publicBase + pathOrUrl.slice(pattern.length);
        }
    }

    return pathOrUrl;
}
