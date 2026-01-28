import Link from 'next/link';
import { notFound } from 'next/navigation';

import { serverApiFetch } from '@/lib/api/server';
import type { CashClosureDetail } from '@/features/reports/types';
import { CashSessionDetailView } from '@/modules/reports/cash/cash-session-detail-view';

type PageProps = {
    params: {
        id: string;
    };
};

export default async function RestauranteCashClosureDetailPage({ params }: PageProps) {
    let closure: CashClosureDetail | null = null;

    try {
        closure = await serverApiFetch<CashClosureDetail>(`/api/v1/reports/cash/closures/${params.id}/`);
    } catch (error) {
        notFound();
    }

    if (!closure) {
        notFound();
    }

    const isClosed = closure.status === 'closed';
    const actionsSlot = (
        <div className="flex flex-wrap justify-end gap-2">
            {isClosed ? (
                <button
                    type="button"
                    disabled
                    title="Próximamente"
                    className="inline-flex items-center rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-500"
                >
                    Exportar
                </button>
            ) : (
                <Link
                    href="/app/operacion/caja"
                    className="inline-flex items-center rounded-full border border-slate-900 px-4 py-2 text-sm font-semibold text-slate-900"
                >
                    Ir a Caja
                </Link>
            )}
        </div>
    );

    return (
        <CashSessionDetailView
            closure={closure}
            backHref="/app/resto/operacion/reportes/caja"
            backLabel="← Volver a Sesiones"
            contextLabel="Caja restaurante"
            actionsSlot={actionsSlot}
        />
    );
}
