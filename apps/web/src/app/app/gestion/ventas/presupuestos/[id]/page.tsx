import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';
import { QuoteDetailClient } from './quote-detail-client';

type Props = {
    params: Promise<{ id: string }>;
};

export default async function QuoteDetailPage({ params }: Props) {
    const { id } = await params;
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.sales !== false;
    const canView = session.permissions?.view_quotes ?? false;
    const canManage = session.permissions?.manage_quotes ?? false;
    const canSend = session.permissions?.send_quotes ?? false;

    if (!featureEnabled) {
        return <AccessMessage title="Tu plan no incluye Ventas" description="Actualizá el plan para ver este presupuesto." />;
    }

    if (!canView) {
        return <AccessMessage title="Sin acceso" description="Tu rol no puede ver los presupuestos." hint="Pedí acceso a un administrador" />;
    }

    return <QuoteDetailClient quoteId={id} canManage={canManage} canSend={canSend} />;
}
