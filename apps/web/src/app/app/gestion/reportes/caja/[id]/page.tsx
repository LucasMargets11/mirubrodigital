import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { serverApiFetch } from '@/lib/api/server';
import { getSession } from '@/lib/auth';
import type { CashClosureDetail } from '@/features/reports/types';
import { CashSessionDetailView } from '@/modules/reports/cash/cash-session-detail-view';

type PageProps = {
    params: {
        id: string;
    };
};

export default async function CashClosureDetailPage({ params }: PageProps) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.reports !== false;
    const canView = session.permissions?.view_reports_cash ?? false;

    if (!featureEnabled) {
        return <AccessMessage title="Tu plan no incluye Reportes" description="Actualizá el plan para ver cierres de caja." />;
    }

    if (!canView) {
        return <AccessMessage title="Sin acceso" description="Tu rol no puede ver reportes de caja." hint="Pedí acceso a un administrador" />;
    }

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
            backHref="/app/gestion/reportes/caja"
            backLabel="← Volver a Cierres"
            contextLabel="Caja"
            actionsSlot={actionsSlot}
            saleDetailHref={(saleId) => `/app/gestion/reportes/ventas/${saleId}`}
            paymentsSaleHref={(saleId) => `/app/gestion/reportes/ventas/${saleId}`}
        />
    );
}
