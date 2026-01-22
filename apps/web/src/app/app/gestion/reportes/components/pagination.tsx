'use client';

type ReportsPaginationProps = {
    count: number;
    limit: number;
    offset: number;
    onChange: (offset: number) => void;
    disabled?: boolean;
};

export function ReportsPagination({ count, limit, offset, onChange, disabled }: ReportsPaginationProps) {
    const totalPages = Math.max(1, Math.ceil(count / limit));
    const currentPage = Math.min(totalPages, Math.floor(offset / limit) + 1);
    const canGoBack = offset > 0;
    const canGoForward = offset + limit < count;

    return (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white/80 px-4 py-2 text-sm text-slate-700">
            <span>
                Página {currentPage} de {totalPages}
            </span>
            <div className="flex items-center gap-2">
                <button
                    type="button"
                    onClick={() => onChange(Math.max(0, offset - limit))}
                    disabled={!canGoBack || disabled}
                    className="rounded-full border border-slate-200 px-3 py-1 font-medium text-slate-600 transition hover:border-slate-300 disabled:cursor-not-allowed disabled:opacity-40"
                >
                    Anterior
                </button>
                <button
                    type="button"
                    onClick={() => onChange(offset + limit)}
                    disabled={!canGoForward || disabled}
                    className="rounded-full border border-slate-200 px-3 py-1 font-medium text-slate-600 transition hover:border-slate-300 disabled:cursor-not-allowed disabled:opacity-40"
                >
                    Siguiente
                </button>
            </div>
        </div>
    );
}
