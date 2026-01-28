import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

export default async function KitchenBoardPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.resto_kitchen !== false;
    const canView = session.permissions?.view_kitchen_board ?? false;

    if (!featureEnabled || !canView) {
        redirect('/app/servicios');
    }

    return (
        <section className="space-y-6">
            <header>
                <p className="text-xs uppercase tracking-wide text-slate-400">Servicio Restaurante</p>
                <h1 className="text-3xl font-semibold text-slate-900">Tablero de cocina</h1>
                <p className="text-sm text-slate-500">
                    Las comandas en tiempo real van a aparecer acá apenas las órdenes pasen a preparación.
                </p>
            </header>
            <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-6 text-sm text-slate-500">
                El tablero de cocina todavía está en desarrollo. Mientras tanto, podés operar las órdenes desde la vista principal
                y actualizar estados desde el salón.
            </div>
        </section>
    );
}
