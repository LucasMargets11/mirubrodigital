import { redirect } from 'next/navigation';
import Link from 'next/link';
import type { Route } from 'next';

import { getSession } from '@/lib/auth';

export default async function ResenasPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const hasReviewsConfig = session.features?.qr_reviews_core === true;

    return (
        <>
            <header>
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-500">
                    QR de Reseñas
                </p>
                <h1 className="text-3xl font-display font-bold text-slate-900">Inicio</h1>
                <p className="text-sm text-slate-500">{session.current.business.name}</p>
            </header>

            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                <Link
                    href={'/app/resenas/configuracion' as Route}
                    className="group rounded-2xl border border-slate-200 bg-white p-6 shadow-sm hover:shadow-md transition-shadow"
                >
                    <h2 className="text-lg font-semibold text-slate-900 group-hover:text-brand-600">
                        Configuración
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                        Configurá tu Google Place ID para que el QR redirija a la
                        página de reseñas de tu negocio.
                    </p>
                </Link>

                <Link
                    href={'/app/resenas/qr' as Route}
                    className="group rounded-2xl border border-slate-200 bg-white p-6 shadow-sm hover:shadow-md transition-shadow"
                >
                    <h2 className="text-lg font-semibold text-slate-900 group-hover:text-brand-600">
                        Mi QR
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                        Generá y descargá tu código QR listo para imprimir.
                    </p>
                </Link>
            </div>
        </>
    );
}
