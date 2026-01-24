"use client";

import { useEffect, useRef, useState } from 'react';

import {
    useApplyInventoryImport,
    useInventoryImport,
    usePreviewInventoryImport,
    useUploadInventoryImport,
} from '@/features/inventory-imports/hooks';
import type {
    InventoryImportJob,
    InventoryImportPreviewResponse,
    InventoryImportPreviewRow,
    InventoryImportSummary,
} from '@/features/inventory-imports/types';
import { ApiError } from '@/lib/api/client';
import { cn } from '@/lib/utils';

const STATUS_COLORS: Record<string, string> = {
    ok: 'bg-emerald-100 text-emerald-700',
    warning: 'bg-amber-100 text-amber-700',
    error: 'bg-rose-100 text-rose-700',
};

export function StockImportClient() {
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [job, setJob] = useState<InventoryImportJob | null>(null);
    const [preview, setPreview] = useState<InventoryImportPreviewResponse | null>(null);
    const [statusMessage, setStatusMessage] = useState<string>('Subí tu Excel para comenzar.');
    const [polling, setPolling] = useState(false);
    const fileInputRef = useRef<HTMLInputElement | null>(null);

    const uploadMutation = useUploadInventoryImport();
    const previewMutation = usePreviewInventoryImport();
    const applyMutation = useApplyInventoryImport();

    const { data: jobRefetched } = useInventoryImport(job?.id, {
        enabled: Boolean(job?.id) && polling,
        refetchInterval: polling ? 3000 : false,
    });

    useEffect(() => {
        if (!jobRefetched) {
            return;
        }
        setJob(jobRefetched);
        if (jobRefetched.status === 'done' || jobRefetched.status === 'failed') {
            setPolling(false);
            setStatusMessage(
                jobRefetched.status === 'done'
                    ? 'Importación finalizada. Revisá el resumen para ver los cambios aplicados.'
                    : 'Importación con errores. Revisá el detalle para corregir el archivo.',
            );
        }
    }, [jobRefetched]);

    const handleSelectFile = (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) {
            setSelectedFile(null);
            return;
        }
        setSelectedFile(file);
    };

    const handleUpload = async () => {
        if (!selectedFile) {
            return;
        }
        try {
            const response = await uploadMutation.mutateAsync(selectedFile);
            setJob(response);
            setPreview(null);
            setStatusMessage('Archivo cargado. Generá la vista previa para revisar los cambios.');
            setPolling(false);
        } catch (error) {
            console.error(error);
            setStatusMessage(resolveApiMessage(error, 'No pudimos subir el archivo. Verificá el formato e intentá nuevamente.'));
        }
    };

    const handlePreview = async () => {
        if (!job) {
            return;
        }
        try {
            const response = await previewMutation.mutateAsync(job.id);
            setPreview(response);
            setStatusMessage('Vista previa lista. Revisá los resultados antes de aplicar.');
        } catch (error) {
            console.error(error);
            setStatusMessage(resolveApiMessage(error, 'No pudimos generar la vista previa. Revisá el archivo e intentá nuevamente.'));
        }
    };

    const handleApply = async () => {
        if (!job) {
            return;
        }
        try {
            const response = await applyMutation.mutateAsync(job.id);
            setJob(response);
            setStatusMessage('Aplicando importación. Este proceso puede tardar unos segundos.');
            setPolling(true);
        } catch (error) {
            console.error(error);
            setStatusMessage(resolveApiMessage(error, 'No pudimos aplicar la importación. Revisá los errores e intentá nuevamente.'));
        }
    };

    const summary: InventoryImportSummary | null = preview?.summary ?? job?.summary ?? null;
    const rows = preview?.rows ?? [];
    const hasErrors = (preview?.summary?.error_count ?? 0) > 0 || rows.some((row) => row.status === 'error');
    const canApply = Boolean(preview) && !hasErrors && !polling;

    const isUploading = uploadMutation.isPending;
    const isPreviewing = previewMutation.isPending;
    const isApplying = applyMutation.isPending || polling;

    const jobStatusLabel = job ? formatStatus(job.status) : 'Pendiente';

    const handleResetFile = () => {
        setSelectedFile(null);
        fileInputRef.current?.value && (fileInputRef.current.value = '');
    };

    return (
        <div className="space-y-6">
            <header className="flex flex-col gap-2">
                <p className="text-xs uppercase tracking-[0.25em] text-slate-400">Importador</p>
                <h1 className="text-2xl font-semibold text-slate-900">Importar stock por Excel</h1>
                <p className="text-sm text-slate-500">
                    Cargá un archivo .xlsx con tus productos para crearlos, actualizarlos y ajustar stock mediante movimientos.
                </p>
            </header>

            <div className="grid gap-4 lg:grid-cols-3">
                <Card title="1. Subí el archivo" description="Formato .xlsx, hasta 10 MB." status={selectedFile?.name ?? 'Sin archivo'}>
                    <div className="space-y-3">
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".xlsx"
                            onChange={handleSelectFile}
                            className="w-full rounded-2xl border border-dashed border-slate-300 px-4 py-6 text-sm text-slate-500 file:mr-4 file:rounded-full file:border-0 file:bg-slate-900 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white"
                            disabled={isUploading || isPreviewing || isApplying}
                        />
                        <div className="flex flex-wrap gap-3">
                            <button
                                type="button"
                                onClick={handleUpload}
                                disabled={!selectedFile || isUploading}
                                className="rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                            >
                                {isUploading ? 'Subiendo...' : 'Subir Excel'}
                            </button>
                            {selectedFile ? (
                                <button
                                    type="button"
                                    onClick={handleResetFile}
                                    className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                                >
                                    Limpiar
                                </button>
                            ) : null}
                        </div>
                        <p className="text-xs text-slate-500">
                            Descargá la plantilla base para completar los campos necesarios.&nbsp;
                            <a
                                href="/plantillas/importar-stock.xlsx"
                                className="font-semibold text-slate-900 underline-offset-2 hover:underline"
                            >
                                Descargar plantilla
                            </a>
                        </p>
                    </div>
                </Card>

                <Card
                    title="2. Revisá la vista previa"
                    description="Te mostraremos hasta 200 filas con acciones y alertas."
                    status={preview ? 'Vista previa generada' : 'Sin vista previa'}
                >
                    <button
                        type="button"
                        onClick={handlePreview}
                        disabled={!job || isPreviewing || isUploading}
                        className="w-full rounded-full border border-slate-900 px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-900 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        {isPreviewing ? 'Generando...' : 'Generar vista previa'}
                    </button>
                    {preview && (
                        <p className="mt-2 text-xs text-slate-500">{rows.length} filas analizadas en esta vista.</p>
                    )}
                </Card>

                <Card
                    title="3. Aplicá los cambios"
                    description="Crearemos productos y movimientos ADJUST automáticos."
                    status={jobStatusLabel}
                >
                    <button
                        type="button"
                        onClick={handleApply}
                        disabled={!canApply || isApplying}
                        className="w-full rounded-full bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                    >
                        {isApplying ? 'Aplicando...' : 'Aplicar importación'}
                    </button>
                    {hasErrors && preview ? (
                        <p className="mt-2 text-xs text-rose-600">Corregí los errores antes de aplicar.</p>
                    ) : null}
                </Card>
            </div>

            <StatusBanner message={statusMessage} status={job?.status} />

            {summary ? <SummaryGrid summary={summary} /> : null}

            {job ? <JobDetails job={job} /> : null}

            {preview ? <PreviewTable rows={rows} /> : null}
        </div>
    );
}

function Card({
    title,
    description,
    status,
    children,
}: {
    title: string;
    description: string;
    status: string;
    children: React.ReactNode;
}) {
    return (
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <header className="space-y-1">
                <p className="text-xs uppercase tracking-[0.3em] text-slate-400">{status}</p>
                <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
                <p className="text-sm text-slate-500">{description}</p>
            </header>
            <div className="mt-4 space-y-3">{children}</div>
        </section>
    );
}

function StatusBanner({ message, status }: { message: string; status?: string }) {
    const tone = status === 'failed' ? 'text-rose-700 bg-rose-50 border-rose-200' : 'text-slate-600 bg-slate-50 border-slate-200';
    return (
        <div className={cn('rounded-3xl border px-4 py-3 text-sm', tone)}>
            <p>{message}</p>
        </div>
    );
}

function SummaryGrid({ summary }: { summary: InventoryImportSummary }) {
    const items = [
        { label: 'Total filas', value: summary.total_rows },
        { label: 'Crear productos', value: summary.create_count },
        { label: 'Actualizar productos', value: summary.update_count },
        { label: 'Ajustar stock', value: summary.adjust_count },
        { label: 'Omitir stock', value: summary.skip_count },
        { label: 'Warnings', value: summary.warning_count },
        { label: 'Errores', value: summary.error_count },
    ];
    return (
        <section className="rounded-3xl border border-slate-200 bg-white/80 p-5 shadow-sm">
            <p className="text-sm font-semibold text-slate-600">Resumen de la vista previa</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {items.map((item) => (
                    <div key={item.label} className="rounded-2xl border border-slate-100 bg-slate-50/60 p-3">
                        <p className="text-xs uppercase tracking-wide text-slate-400">{item.label}</p>
                        <p className="text-2xl font-semibold text-slate-900">{item.value ?? 0}</p>
                    </div>
                ))}
            </div>
        </section>
    );
}

function JobDetails({ job }: { job: InventoryImportJob }) {
    return (
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <header className="flex flex-col gap-1">
                <h3 className="text-lg font-semibold text-slate-900">Detalle del importador</h3>
                <p className="text-sm text-slate-500">Archivo {job.filename} • Estado {formatStatus(job.status)}</p>
            </header>
            <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 text-sm text-slate-600">
                <InfoRow label="Creaciones" value={job.created_count} />
                <InfoRow label="Actualizaciones" value={job.updated_count} />
                <InfoRow label="Ajustes" value={job.adjusted_count} />
                <InfoRow label="Omisiones" value={job.skipped_count} />
                <InfoRow label="Errores" value={job.error_count} />
                <InfoRow label="Actualizado" value={new Date(job.updated_at).toLocaleString('es-AR', { dateStyle: 'medium', timeStyle: 'short' })} />
            </dl>
            {job.errors && job.errors.length > 0 ? (
                <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                    <p className="font-semibold">Errores del proceso</p>
                    <ul className="list-disc pl-5">
                        {job.errors.map((error, index) => (
                            <li key={`${error}-${index}`}>{error}</li>
                        ))}
                    </ul>
                </div>
            ) : null}
            {job.result_url ? (
                <a
                    href={job.result_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-4 inline-flex items-center justify-center rounded-full border border-slate-900 px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-900 hover:text-white"
                >
                    Descargar reporte completo
                </a>
            ) : null}
        </section>
    );
}

function InfoRow({ label, value }: { label: string; value: string | number }) {
    return (
        <div className="rounded-2xl border border-slate-100 bg-slate-50/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
            <p className="text-lg font-semibold text-slate-900">{value}</p>
        </div>
    );
}

function PreviewTable({ rows }: { rows: InventoryImportPreviewRow[] }) {
    return (
        <section className="space-y-3 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <header className="flex flex-col gap-1">
                <h3 className="text-lg font-semibold text-slate-900">Vista previa (máx. 200 filas)</h3>
                <p className="text-sm text-slate-500">
                    Revisá los estados antes de aplicar. Los movimientos de stock se crearán sólo cuando haya cambios.
                </p>
            </header>
            <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-100 text-sm">
                    <thead>
                        <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                            <th className="px-3 py-2">Línea</th>
                            <th className="px-3 py-2">Producto</th>
                            <th className="px-3 py-2">SKU</th>
                            <th className="px-3 py-2">Acción</th>
                            <th className="px-3 py-2">Stock</th>
                            <th className="px-3 py-2">Estado</th>
                            <th className="px-3 py-2">Mensajes</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {rows.map((row) => (
                            <tr key={`${row.line_number}-${row.name}`}>
                                <td className="px-3 py-2 text-slate-500">{row.line_number}</td>
                                <td className="px-3 py-2 font-semibold text-slate-900">{row.name}</td>
                                <td className="px-3 py-2 text-slate-500">{row.sku || '—'}</td>
                                <td className="px-3 py-2 text-slate-500">{formatAction(row.action)}</td>
                                <td className="px-3 py-2 text-slate-500">{formatStockAction(row.stock_action)}</td>
                                <td className="px-3 py-2">
                                    <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-semibold', STATUS_COLORS[row.status] ?? 'bg-slate-200 text-slate-600')}>
                                        {row.status.toUpperCase()}
                                    </span>
                                </td>
                                <td className="px-3 py-2">
                                    {row.messages?.length ? (
                                        <ul className="list-disc space-y-1 pl-4 text-xs text-slate-600">
                                            {row.messages.map((message, index) => (
                                                <li key={`${message}-${index}`}>{message}</li>
                                            ))}
                                        </ul>
                                    ) : (
                                        <span className="text-xs text-slate-400">Sin mensajes</span>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </section>
    );
}

function formatStatus(status: InventoryImportJob['status']) {
    switch (status) {
        case 'pending':
            return 'Pendiente';
        case 'processing':
            return 'Procesando';
        case 'done':
            return 'Completado';
        case 'failed':
            return 'Fallido';
        default:
            return status;
    }
}

function formatAction(action: InventoryImportPreviewRow['action']) {
    return action === 'create' ? 'Crear' : 'Actualizar';
}

function formatStockAction(action: InventoryImportPreviewRow['stock_action']) {
    return action === 'adjust' ? 'Ajustar stock' : 'Sin cambios';
}

function resolveApiMessage(error: unknown, fallback: string) {
    if (error instanceof ApiError && error.message) {
        return error.message;
    }
    if (error instanceof Error && error.message) {
        return error.message;
    }
    return fallback;
}
