import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Middleware — sets x-pathname header so server components can read the
 * current path via `headers().get('x-pathname')`.
 *
 * This is required because Next.js App Router server components cannot access
 * the current URL directly.  The layout enforcement gate in /app/layout.tsx
 * uses x-pathname to detect billing-bypass paths (/app/planes, /app/servicios)
 * and avoid redirect loops.
 */
export function middleware(request: NextRequest) {
    const response = NextResponse.next();
    response.headers.set('x-pathname', request.nextUrl.pathname);
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
