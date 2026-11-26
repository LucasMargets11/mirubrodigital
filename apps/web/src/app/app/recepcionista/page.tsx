import Link from 'next/link';
import { redirect } from 'next/navigation';

import { AIUsageSummaryPanel } from '@/features/reception/ai-usage-summary-panel';
import { getSession } from '@/lib/auth';

const SECONDARY_LINK =
    'rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50';

export default async function RecepcionistaPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canViewUsage = session.permissions?.view_ai_usage === true;
    const canViewCustomers = session.features?.customers === true && session.permissions?.view_customers === true;

    return (
        <section className="space-y-4">
            <header>
                <h1 className="text-2xl font-semibold text-slate-900">Recepcionista IA</h1>
                <p className="text-sm text-slate-500">
                    Tu agente atiende por WhatsApp y te deja cada consulta lista para seguir desde MiRubro.
                </p>
            </header>

            {(canViewUsage || canViewCustomers) && (
                <nav aria-label="Accesos de Recepcionista IA" className="flex flex-wrap gap-2">
                    {canViewUsage && (
                        <Link href="/app/recepcionista/consumo" className={SECONDARY_LINK}>
                            Ver consumo
                        </Link>
                    )}
                    {canViewCustomers && (
                        <Link href="/app/clientes" className={SECONDARY_LINK}>
                            Ver clientes
                        </Link>
                    )}
                </nav>
            )}

            {canViewUsage && <AIUsageSummaryPanel variant="compact" />}
        </section>
    );
}
