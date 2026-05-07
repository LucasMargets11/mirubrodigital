import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const isDev = process.env.NODE_ENV === 'development';

/**
 * CSP directives in report-only mode.
 *
 * Next.js injects inline scripts for hydration and uses style-loader with
 * inline styles in development, so we allow 'unsafe-inline' for both to
 * avoid breaking the UI.  Once a nonce strategy is in place these can be
 * tightened.
 *
 * 'unsafe-eval' is only included in development (Next.js hot-reload needs it).
 * connect-src uses localhost/api:8000 in dev; in prod it uses NEXT_PUBLIC_API_URL.
 */
const apiOrigin = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const connectSrc = isDev
    ? "connect-src 'self' http://localhost:8000 http://api:8000 https://accounts.google.com/gsi/"
    : `connect-src 'self' ${apiOrigin} https://accounts.google.com/gsi/`;

const scriptSrc = isDev
    ? "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://accounts.google.com/gsi/client"
    : "script-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/client";

const CSP_DIRECTIVES = [
    "default-src 'self'",
    scriptSrc,
    "style-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/style",
    "img-src 'self' data: https://via.placeholder.com https://images.unsplash.com",
    "font-src 'self' data:",
    connectSrc,
    "frame-src 'self' https://accounts.google.com https://accounts.google.com/gsi/",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
].join('; ');

/**
 * Middleware — sets x-pathname header so server components can read the
 * current path via `headers().get('x-pathname')`.
 *
 * This is required because Next.js App Router server components cannot access
 * the current URL directly.  The layout enforcement gate in /app/layout.tsx
 * uses x-pathname to detect billing-bypass paths (/app/planes, /app/servicios)
 * and avoid redirect loops.
 *
 * Also sets Content-Security-Policy-Report-Only for observability (Phase 2C).
 */
// Routes where Google Identity Services OAuth popup is used.
const GOOGLE_SIGNIN_PATHS = ['/entrar', '/registrarse'];

export function middleware(request: NextRequest) {
    const response = NextResponse.next();
    response.headers.set('x-pathname', request.nextUrl.pathname);
    response.headers.set('Content-Security-Policy-Report-Only', CSP_DIRECTIVES);

    // Allow the Google Sign-In popup to postMessage back to this page.
    // Only needed on pages that initiate the Google OAuth flow.
    const pathname = request.nextUrl.pathname;
    if (GOOGLE_SIGNIN_PATHS.some((p) => pathname === p || pathname.startsWith(p + '/'))) {
        response.headers.set('Cross-Origin-Opener-Policy', 'same-origin-allow-popups');
    }

    return response;
}

export const config = {
    matcher: [
        /*
         * Match all paths except static files and Next.js internals.
         * This keeps the middleware lightweight and fast.
         */
        '/((?!_next/static|_next/image|favicon.ico|logo/).*)',
    ],
};
