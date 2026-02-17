import { ReactNode } from 'react';
import { MarketingNav } from '@/components/navigation/marketing-nav';
import { MarketingFooter } from '@/components/navigation/marketing-footer';

export default function MarketingLayout({ children }: { children: ReactNode }) {
    return (
        <div className="min-h-screen flex flex-col bg-white text-slate-900">
            <MarketingNav />

            <main className="flex-1 flex flex-col">
                {children}
            </main>

            <MarketingFooter />
        </div>
    );
}
