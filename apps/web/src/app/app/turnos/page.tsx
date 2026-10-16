import Link from 'next/link';
import { redirect } from 'next/navigation';

import { PublicBookingLinkCard } from '@/features/appointments/public-booking-link-card';
import { getSession } from '@/lib/auth';

import { WhatsappContactCard } from './whatsapp-contact-card';

export default async function TurnosPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canManageSettings = Boolean(session.permissions?.manage_settings);

    return (
        <section className="space-y-4">
            <header>
                <h1 className="text-2xl font-semibold text-slate-900">Turnos</h1>
                <p className="text-sm text-slate-500">
                    Gestioná tu agenda, servicios y reservas desde MiRubro.
                </p>
            </header>

            <nav aria-label="Accesos de Turnos" className="flex flex-wrap gap-2">
                <Link
                    href="/app/turnos/turnos"
                    className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
                >
                    Ver turnos
                </Link>
                {canManageSettings && (
                    <Link
                        href="/app/turnos/configuracion"
                        className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                    >
                        Configuración
                    </Link>
                )}
            </nav>

            <PublicBookingLinkCard publicBooking={session.current.business.public_booking} />

            {canManageSettings && (
                <Link
                    href="/app/turnos/configuracion"
                    className="block rounded-2xl border border-slate-200 bg-white p-4 shadow-sm hover:border-slate-300"
                >
                    <span className="text-sm font-semibold text-slate-800">Mercado Pago</span>
                    <span className="block text-xs text-slate-500">
                        Conectá tu cuenta para recibir las señas de tus reservas directamente.
                    </span>
                </Link>
            )}

            {canManageSettings && <WhatsappContactCard />}
        </section>
    );
}
