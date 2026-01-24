"use client";

import { useMemo, useState } from 'react';

import { CashSessionBanner } from '@/features/cash/components/cash-session-banner';
import { CashSummaryCards } from '@/features/cash/components/cash-summary-cards';
import { CollectAllPendingModal } from '@/features/cash/components/collect-all-pending-modal';
import { CollectPaymentModal } from '@/features/cash/components/collect-payment-modal';
import { OpenCashModal } from '@/features/cash/components/open-session-modal';
import { PendingSalesCallout } from '@/features/cash/components/pending-sales-callout';
import { SalesToCollectTable } from '@/features/cash/components/sales-to-collect-table';
import type { SalesWithBalance } from '@/features/cash/types';
import { useCashSummary } from '@/features/cash/hooks';
import { useSales } from '@/features/gestion/hooks';
import type { SalesFilters } from '@/features/gestion/types';

type CashHomeClientProps = {
    canManage: boolean;
    canCollect: boolean;
};

type FilterValue = 'pending' | 'paid' | 'all';

export function CashHomeClient({ canManage, canCollect }: CashHomeClientProps) {
    const [openModal, setOpenModal] = useState(false);
    const [collectSale, setCollectSale] = useState<SalesWithBalance | null>(null);
    const [filter, setFilter] = useState<FilterValue>('pending');
    const [collectAllOpen, setCollectAllOpen] = useState(false);

    const today = new Date().toISOString().slice(0, 10);
    const filters: SalesFilters = useMemo(
        () => ({ status: 'completed', date_from: today, date_to: today }),
        [today]
    );

    const summaryQuery = useCashSummary();
    const session = summaryQuery.data?.session ?? null;
    const pendingCount = session?.totals?.pending_sales_count ?? 0;
    const pendingTotal = session?.totals?.pending_sales_total ?? '0';

    const salesQuery = useSales(filters);
    const sales = (salesQuery.data?.results ?? []) as SalesWithBalance[];

    const handleCollect = (sale: SalesWithBalance) => {
        setCollectSale(sale);
    };

    return (
        <div className="space-y-6">
            <CashSessionBanner
                session={session}
                loading={summaryQuery.isLoading}
                canManage={canManage}
                onOpenRequest={() => setOpenModal(true)}
            />
            {summaryQuery.isError ? (
                <p className="rounded-3xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                    No pudimos actualizar el estado de la caja. Intentá nuevamente.
                </p>
            ) : null}
            <CashSummaryCards session={session} loading={summaryQuery.isFetching && !summaryQuery.data} />
            {session && pendingCount > 0 ? (
                <PendingSalesCallout
                    pendingCount={pendingCount}
                    pendingTotal={pendingTotal}
                    canCollect={canCollect}
                    onCollectAll={() => setCollectAllOpen(true)}
                />
            ) : null}
            {salesQuery.isError ? (
                <p className="rounded-3xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                    No pudimos cargar las ventas del día. Intentá nuevamente.
                </p>
            ) : null}
            <SalesToCollectTable
                sales={sales}
                loading={salesQuery.isLoading}
                canCollect={canCollect && Boolean(session)}
                filter={filter}
                onFilterChange={(value) => setFilter(value)}
                onCollect={handleCollect}
            />
            <OpenCashModal open={openModal} onClose={() => setOpenModal(false)} canManage={canManage} />
            <CollectPaymentModal
                open={Boolean(collectSale)}
                onClose={() => setCollectSale(null)}
                sale={collectSale}
                sessionId={session?.id}
                canManage={canCollect}
            />
            <CollectAllPendingModal
                open={collectAllOpen}
                onClose={() => setCollectAllOpen(false)}
                session={session}
                canCollect={canCollect}
            />
        </div>
    );
}
