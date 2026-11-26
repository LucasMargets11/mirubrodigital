import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { AIUsageSummaryPanel } from '@/features/reception/ai-usage-summary-panel';
import { getSession } from '@/lib/auth';

export default async function RecepcionistaConsumoPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    if (session.permissions?.view_ai_usage !== true) {
        return (
            <AccessMessage
                title="Sin acceso"
                description="Tu rol no puede ver el consumo de Recepcionista IA."
                hint="Solicitá permisos a un administrador"
            />
        );
    }

    return (
        <section className="space-y-4">
            <header>
                <h1 className="text-2xl font-semibold text-slate-900">Consumo</h1>
                <p className="text-sm text-slate-500">Conversaciones usadas por tu agente en el período actual.</p>
            </header>
            <AIUsageSummaryPanel variant="full" />
        </section>
    );
}
