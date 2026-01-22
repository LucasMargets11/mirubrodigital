"use client";

import { CashSummaryCards } from '@/features/cash/components/cash-summary-cards';
import { CloseCashForm } from '@/features/cash/components/close-cash-form';
import { useCashSummary } from '@/features/cash/hooks';

type CierreClientProps = {
    canManage: boolean;
};

export function CierreClient({ canManage }: CierreClientProps) {
    const summaryQuery = useCashSummary();
    const session = summaryQuery.data?.session ?? null;

    return (
        <div className="space-y-6">
            <CashSummaryCards session={session} loading={summaryQuery.isLoading} />
            <CloseCashForm session={session} canManage={canManage} />
        </div>
    );
}
