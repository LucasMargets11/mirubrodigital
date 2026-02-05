import { ReactNode } from 'react';
import { FinanceHeader, FinanceTabs } from './components/header';

export default function FinanzasLayout({ children }: { children: ReactNode }) {
    return (
        <div className="space-y-6">
            <FinanceHeader />
            <FinanceTabs />
            <div className="min-h-[400px]">
                {children}
            </div>
        </div>
    );
}
