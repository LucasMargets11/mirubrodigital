import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

import { ReportsSummaryClient } from './summary-client';

export default async function ReportsSummaryPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canViewStock = session.permissions?.view_stock ?? false;
    const hasInventoryFeature = session.features?.inventory !== false;

    return <ReportsSummaryClient canViewStock={canViewStock} hasInventoryFeature={hasInventoryFeature} />;
}
