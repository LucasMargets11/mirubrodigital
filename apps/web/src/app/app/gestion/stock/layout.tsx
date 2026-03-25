import { ReactNode } from 'react';
import { StockHeader } from './stock-header';

export default function StockLayout({ children }: { children: ReactNode }) {
    return (
        <section className="space-y-6">
            <StockHeader />
            {children}
        </section>
    );
}
