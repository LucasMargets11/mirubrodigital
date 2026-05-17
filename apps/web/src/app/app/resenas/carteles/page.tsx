import { redirect } from 'next/navigation';
import type { Route } from 'next';

import { getSession } from '@/lib/auth';
import { QrPostersClient } from './qr-posters-client';

export default async function CartelesQrPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canView = session.permissions?.manage_reviews ?? false;
    if (!canView) {
        redirect('/app/resenas' as Route);
    }

    return (
        <>
            <header className="space-y-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-500">
                    QR de Reseñas PRO
                </p>
                <h1 className="text-3xl font-display font-bold text-slate-900">
                    Carteles QR
                </h1>
                <p className="text-sm text-slate-500">
                    Generá un cartel imprimible con tu QR de reseñas ·{' '}
                    <span className="font-medium text-slate-700">
                        {session.current.business.name}
                    </span>
                </p>
            </header>

            <QrPostersClient businessName={session.current.business.name} />
        </>
    );
}
