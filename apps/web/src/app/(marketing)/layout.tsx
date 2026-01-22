import { ReactNode } from 'react';
import { MarketingNav } from '@/components/navigation/marketing-nav';
import { MarketingFooter } from '@/components/navigation/marketing-footer';

export default function MarketingLayout({ children }: { children: ReactNode }) {
    return (
        <div className="mx-auto flex min-h-screen max-w-5xl flex-col px-6">
            <MarketingNav />
            <main className="flex-1 py-12">{children}</main>
            <MarketingFooter />
        </div>
    );
}
