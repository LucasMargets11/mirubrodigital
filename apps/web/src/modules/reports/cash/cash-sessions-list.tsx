'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { useCashClosures } from '@/features/reports/hooks';
import type { CashClosure } from '@/features/reports/types';
import { downloadCsv } from '@/lib/csv';
import { formatCurrency } from '@/lib/format';
import { ReportsFilters, type ReportsFiltersValue, type StatusOption } from '@/modules/reports/components/filters';
import { ReportsPagination } from '@/modules/reports/components/pagination';

type CashSessionsListProps = {
    eyebrow?: string;
    title?: string;
    description?: string;
    detailHref: (id: string) => string;
    emptyMessage?: string;
    exportFilePrefix?: string;
    filtersConfig?: {
        showStatus?: boolean;
        statusOptions?: StatusOption[];
        defaultStatus?: string;
        showRegister?: boolean;
        showUser?: boolean;
        showSearch?: boolean;
        searchPlaceholder?: string;
    };
    ctaLabel?: string;
};

const defaultRange = getDefaultRange();

export const cashSessionStatusOptions: StatusOption[] = [
    { value: 'all', label: 'Todas' },
    { value: 'open', label: 'Abiertas' },
    { value: 'closed', label: 'Cerradas' },
];

export function CashSessionsList({
    eyebrow = 'Caja',
    title = 'Sesiones de caja',
    description = 'Controlá la actividad de tus cajas.',
    detailHref,
    emptyMessage = 'No hay sesiones registradas.',
    exportFilePrefix = 'cajas',
    filtersConfig,
    ctaLabel = 'Ver detalle',
}: CashSessionsListProps) {
    const defaultStatus = filtersConfig?.defaultStatus ?? 'closed';
    const [filters, setFilters] = useState<ReportsFiltersValue>({
        preset: 'last7',
        from: defaultRange.from,
        to: defaultRange.to,
        status: defaultStatus,
    });
    const [limit] = useState(20);
    const [offset, setOffset] = useState(0);

    useEffect(() => {
        setOffset(0);
    }, [filters]);

    const queryFilters = useMemo(
        () => ({
            from: filters.from,
            to: filters.to,
            register_id: filters.registerId,
            user_id: filters.userId,
            status: filters.status,
            q: filters.query,
            limit,
            offset,
        }),
        [filters, limit, offset],
    );

    const { data, isLoading, isError } = useCashClosures(queryFilters);

    const handleExport = () => {
        if (!data?.results?.length) {
            return;
        }
        downloadCsv(`${exportFilePrefix}-${filters.from}-${filters.to}`, [
            {
                title: 'Sesiones de caja',
                headers: ['Fecha apertura', 'Fecha cierre', 'Caja', 'Estado', 'Esperado', 'Contado', 'Diferencia'],
                rows: data.results.map((closure) => [
                    formatDate(closure.opened_at),
                    closure.closed_at ? formatDate(closure.closed_at) : 'Abierta',
                    closure.register?.name ?? '—',
                    closure.status,
                    closure.expected_cash ?? closure.opening_cash_amount ?? '0',
                    closure.counted_cash ?? '0',
                    closure.difference ?? '0',
                ]),
            },
        ]);
    };

    const showStatus = filtersConfig?.showStatus ?? true;
    const statusOptions = filtersConfig?.statusOptions ?? cashSessionStatusOptions;
    const showRegister = filtersConfig?.showRegister ?? false;
    const showUser = filtersConfig?.showUser ?? false;
    const showSearch = filtersConfig?.showSearch ?? false;
    const searchPlaceholder = filtersConfig?.searchPlaceholder;

    return (
        <div className="space-y-6">
            <ReportsFilters
                value={filters}
                onChange={setFilters}
                showStatus={showStatus}
                statusOptions={statusOptions}
                showRegister={showRegister}
                showUser={showUser}
                showSearch={showSearch}
                searchPlaceholder={searchPlaceholder}
            />

            <section className="rounded-3xl border border-slate-200 bg-white/80 p-4 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">{eyebrow}</p>
                        <h2 className="text-2xl font-semibold text-slate-900">{title}</h2>
                        {description ? <p className="text-sm text-slate-500">{description}</p> : null}
                    </div>
                    <button
                        type="button"
                        onClick={handleExport}
                        className="inline-flex items-center gap-2 rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-400 hover:text-slate-900"
                    >
                        Exportar CSV
                    </button>
                </div>

                {isError && (
                    <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                        Error al cargar sesiones de caja.
                    </div>
                )}

                <div className="mt-6 overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-left text-slate-500">
                                <th className="px-2 py-2 font-medium">Apertura</th>
                                <th className="px-2 py-2 font-medium">Cierre</th>
                                <th className="px-2 py-2 font-medium">Caja</th>
                                <th className="px-2 py-2 font-medium">Estado</th>
                                <th className="px-2 py-2 font-medium text-right">Esperado</th>
                                <th className="px-2 py-2 font-medium text-right">Contado</th>
                                <th className="px-2 py-2 font-medium text-right">Diferencia</th>
                                <th className="px-2 py-2" />
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading && (
                                <tr>
                                    <td colSpan={8} className="px-2 py-6 text-center text-slate-500">
                                        Cargando sesiones...
                                    </td>
                                </tr>
                            )}
                            {!isLoading && !data?.results?.length && (
                                <tr>
                                    <td colSpan={8} className="px-2 py-6 text-center text-slate-500">
                                        {emptyMessage}
                                    </td>
                                </tr>
                            )}
                            {(data?.results ?? []).map((closure) => (
                                <SessionRow key={closure.id} closure={closure} detailHref={detailHref} ctaLabel={ctaLabel} />
                            ))}
                        </tbody>
                    </table>
                </div>

                <div className="mt-4">
                    <ReportsPagination
                        count={data?.count ?? 0}
                        limit={limit}
                        offset={offset}
                        onChange={setOffset}
                        disabled={isLoading}
                    />
                </div>
            </section>
        </div>
    );
}

type SessionRowProps = {
    closure: CashClosure;
    detailHref: (id: string) => string;
    ctaLabel: string;
};

function SessionRow({ closure, detailHref, ctaLabel }: SessionRowProps) {
    return (
        <tr className="border-t border-slate-100 text-slate-700">
            <td className="px-2 py-3">
                <p className="font-semibold">{formatDate(closure.opened_at)}</p>
                <p className="text-xs text-slate-500">Apertura: {closure.opened_by_name || closure.opened_by?.name || '—'}</p>
            </td>
            <td className="px-2 py-3">
                {closure.closed_at ? (
                    <>
                        <p className="font-semibold">{formatDate(closure.closed_at)}</p>
                        <p className="text-xs text-slate-500">Cierre: {closure.closed_by?.name ?? '—'}</p>
                    </>
                ) : (
                    <span className="text-xs font-semibold text-amber-600">Sesión abierta</span>
                )}
            </td>
            <td className="px-2 py-3">
                <p className="font-medium">{closure.register?.name ?? '—'}</p>
                <p className="text-xs text-slate-500">{closure.note || 'Sin notas'}</p>
            </td>
            <td className="px-2 py-3">
                <StatusPill status={closure.status} />
            </td>
            <td className="px-2 py-3 text-right font-medium">{formatCurrency(closure.expected_cash ?? closure.opening_cash_amount)}</td>
            <td className="px-2 py-3 text-right font-medium">{formatCurrency(closure.counted_cash)}</td>
            <td className="px-2 py-3 text-right font-semibold">
                <Difference value={closure.difference} />
            </td>
            <td className="px-2 py-3 text-right">
                <Link
                    href={detailHref(closure.id)}
                    className="text-sm font-medium text-slate-900 underline-offset-4 hover:underline"
                >
                    {ctaLabel}
                </Link>
            </td>
        </tr>
    );
}

function getDefaultRange() {
    const to = new Date();
    const from = new Date();
    from.setDate(to.getDate() - 6);
    return { from: toIso(from), to: toIso(to) };
}

function toIso(date: Date) {
    return date.toISOString().slice(0, 10);
}

function formatDate(value: string) {
    return new Intl.DateTimeFormat('es-AR', {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(new Date(value));
}

type StatusPillProps = {
    status: CashClosure['status'];
};

function StatusPill({ status }: StatusPillProps) {
    const isClosed = status === 'closed';
    const styles = isClosed
        ? 'bg-emerald-50 text-emerald-700 border border-emerald-100'
        : 'bg-amber-50 text-amber-700 border border-amber-100';
    const label = isClosed ? 'Cerrada' : 'Abierta';
    return <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${styles}`}>{label}</span>;
}

function Difference({ value }: { value: string | null }) {
    const numeric = Number(value ?? 0);
    const styles =
        numeric === 0
            ? 'text-slate-500'
            : numeric > 0
                ? 'text-emerald-600'
                : 'text-rose-600';
    return <span className={styles}>{formatCurrency(numeric)}</span>;
}
