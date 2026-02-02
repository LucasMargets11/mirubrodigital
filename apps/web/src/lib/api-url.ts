export function getServerApiBaseUrl() {
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

export function getClientApiBaseUrl() {
    return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
}
