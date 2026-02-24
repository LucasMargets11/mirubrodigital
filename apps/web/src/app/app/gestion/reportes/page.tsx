import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { todayDateString, dateOffsetFromToday } from '@/lib/dates';

import { ReportsSummaryClient } from './summary-client';

function getServerDefaultRange() {
    return { from: dateOffsetFromToday(-6), to: todayDateString() };
}

export default async function ReportsSummaryPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canViewStock = session.permissions?.view_stock ?? false;
    const hasInventoryFeature = session.features?.inventory !== false;
    const initialRange = getServerDefaultRange();

    return (
        <ReportsSummaryClient
            canViewStock={canViewStock}
            hasInventoryFeature={hasInventoryFeature}
            initialFrom={initialRange.from}
            initialTo={initialRange.to}
        />
    );
}
