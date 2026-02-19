import { ReactNode } from 'react';
import { MarketingNav } from '@/components/navigation/marketing-nav';

/**
 * Auth Layout - NO includes footer
 * Used for /entrar and other auth pages where we want full-height content
 * 
 * Structure:
 * - Header: fixed, 64px (h-16)
 * - Main: takes remaining viewport height (flex-1)
 * - NO Footer: intentionally omitted so content can fill screen
 */

// Header fixed height - single source of truth
const HEADER_HEIGHT = 64; // 16 * 4px = 64px (h-16 in marketing-nav.tsx)

export default function AuthLayout({ children }: { children: ReactNode }) {
    return (
        <div className="min-h-dvh flex flex-col bg-white text-slate-900">
            <MarketingNav />

            {/* Main takes all remaining space, compensates for fixed header */}
            <main className="flex-1 flex flex-col" style={{ paddingTop: `${HEADER_HEIGHT}px` }}>
                {children}
            </main>

            {/* NO Footer - intentionally omitted for full-height auth pages */}
        </div>
    );
}
