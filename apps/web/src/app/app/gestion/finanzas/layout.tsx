import { ReactNode } from 'react';
import { FinanzasNav } from './components/header';

export default function FinanzasLayout({ children }: { children: ReactNode }) {
    return (
        <div className="space-y-6">
            <FinanzasNav />
            <div>
                {children}
            </div>
        </div>
    );
}
