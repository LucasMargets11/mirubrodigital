import { ReactNode } from 'react';
import { MarketingNav } from '@/components/navigation/marketing-nav';
import { MarketingFooter } from '@/components/navigation/marketing-footer';

export default function MarketingLayout({ children }: { children: ReactNode }) {
    return (
        <div className="flex flex-1 flex-col bg-white text-slate-900">
            <MarketingNav />

            <main className="flex flex-1 flex-col">
                <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-6 py-12 md:px-10 lg:max-w-7xl lg:px-12">
                    {children}
                </div>
            </main>

            <MarketingFooter />
        </div>
    );
}
