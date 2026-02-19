import { ReactNode } from 'react';
import { MarketingNav } from '@/components/navigation/marketing-nav';
import { MarketingFooter } from '@/components/navigation/marketing-footer';

// Header fixed height - single source of truth
const HEADER_HEIGHT = 64; // 16 * 4px = 64px (h-16)

export default function MarketingLayout({ children }: { children: ReactNode }) {
    return (
        <div className="min-h-dvh flex flex-col bg-white text-slate-900">
            <MarketingNav />

            {/* Main takes remaining space, compensates for fixed header */}
            <main className="flex-1 flex flex-col" style={{ paddingTop: `${HEADER_HEIGHT}px` }}>
                {children}
            </main>

            <MarketingFooter />
        </div>
    );
}
