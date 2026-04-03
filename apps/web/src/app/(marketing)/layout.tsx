import { ReactNode } from 'react';
import { MarketingNav } from '@/components/navigation/marketing-nav';
import { MarketingFooter } from '@/components/navigation/marketing-footer';

export default function MarketingLayout({ children }: { children: ReactNode }) {
    return (
        <div className="min-h-dvh flex flex-col bg-white text-slate-900">
            <MarketingNav />

            {/* Main takes remaining space, compensates for fixed header with responsive padding */}
            <main className="flex-1 flex flex-col pt-20 lg:pt-24">
                {children}
            </main>

            <MarketingFooter />
        </div>
    );
}
