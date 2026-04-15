import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { ReviewsDashboardClient } from './dashboard-client';

export default async function ResenasPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    return (
        <>
            <header className="space-y-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-500">
                    QR de Reseñas
                </p>
                <h1 className="text-3xl font-display font-bold text-slate-900">
                    Dashboard
                </h1>
                <p className="text-sm text-slate-500">
                    Resumen operativo de reseñas ·{' '}
                    <span className="font-medium text-slate-700">{session.current.business.name}</span>
                </p>
            </header>

            <ReviewsDashboardClient />
        </>
    );
}
