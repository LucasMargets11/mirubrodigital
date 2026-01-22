"use client";

import { MovementsForm } from '@/features/cash/components/movements-form';
import { MovementsTable } from '@/features/cash/components/movements-table';
import { useCashMovements, useCashSummary } from '@/features/cash/hooks';

type MovimientosClientProps = {
    canManage?: boolean;
};

export function MovimientosClient({ canManage = true }: MovimientosClientProps) {
    const summaryQuery = useCashSummary();
    const session = summaryQuery.data?.session ?? null;

    const movementsQuery = useCashMovements({ sessionId: session?.id }, Boolean(session?.id));
    const movements = movementsQuery.data ?? [];

    return (
        <div className="space-y-6">
            <MovementsForm sessionId={session?.id} canManage={canManage} />
            <MovementsTable movements={movements} loading={movementsQuery.isLoading} />
        </div>
    );
}
