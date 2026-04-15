import { redirect } from 'next/navigation';
import type { Route } from 'next';

import { getSession } from '@/lib/auth';
import { AnalyticsClient } from './analytics-client';

export default async function ResenasAnalyticsPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canManage = session.permissions?.manage_reviews ?? false;
    if (!canManage) {
        redirect('/app/resenas' as Route);
    }

    return (
        <>
            <header>
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-500">
                    QR de Reseñas
                </p>
                <h1 className="text-3xl font-display font-bold text-slate-900">Analytics</h1>
                <p className="mt-1 text-sm text-slate-500">
                    Métricas avanzadas de reseñas y conversión.
                </p>
            </header>

            <AnalyticsClient />
        </>
    );
}
