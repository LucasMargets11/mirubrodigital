"use client";

import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Download,
  FileArchive,
  FileSpreadsheet,
  BarChart3,
  Loader2,
  AlertCircle,
} from 'lucide-react';

import {
  getMonthlyReport,
  downloadExportCsv,
  downloadExportZip,
  taxBackupExportKeys,
  type ExportParams,
  type TaxStatus,
  type MonthlyReport,
} from '@/lib/api/tax-backup';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import { TAX_STATUS_CONFIG } from './constants';

// ── Helpers ──────────────────────────────────────────────────────────────────

const MONTHS = [
  { value: 1, label: 'Enero' },
  { value: 2, label: 'Febrero' },
  { value: 3, label: 'Marzo' },
  { value: 4, label: 'Abril' },
  { value: 5, label: 'Mayo' },
  { value: 6, label: 'Junio' },
  { value: 7, label: 'Julio' },
  { value: 8, label: 'Agosto' },
  { value: 9, label: 'Septiembre' },
  { value: 10, label: 'Octubre' },
  { value: 11, label: 'Noviembre' },
  { value: 12, label: 'Diciembre' },
];

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: 5 }, (_, i) => CURRENT_YEAR - i);

const STATUS_OPTIONS: { value: TaxStatus | ''; label: string }[] = [
  { value: '', label: 'Todos los estados' },
  ...Object.entries(TAX_STATUS_CONFIG).map(([value, cfg]) => ({
    value: value as TaxStatus,
    label: cfg.label,
  })),
];

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ── Component ────────────────────────────────────────────────────────────────

export function TaxBackupExports() {
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());
  const [statusFilter, setStatusFilter] = useState<TaxStatus | ''>('');
  const [downloading, setDownloading] = useState<'csv' | 'zip' | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const params: ExportParams = {
    month,
    year,
    ...(statusFilter ? { tax_status: statusFilter } : {}),
  };

  const {
    data: report,
    isLoading,
    isError,
  } = useQuery({
    queryKey: taxBackupExportKeys.monthlyReport(params),
    queryFn: () => getMonthlyReport(params),
  });

  const handleDownload = useCallback(
    async (type: 'csv' | 'zip') => {
      setDownloading(type);
      setDownloadError(null);
      try {
        const blob =
          type === 'csv'
            ? await downloadExportCsv(params)
            : await downloadExportZip(params);

        const ext = type === 'csv' ? 'csv' : 'zip';
        const filename = `respaldo_impositivo_${year}_${String(month).padStart(2, '0')}.${ext}`;
        triggerDownload(blob, filename);
      } catch (err: any) {
        setDownloadError(
          err?.message || `Error al descargar ${type.toUpperCase()}`,
        );
      } finally {
        setDownloading(null);
      }
    },
    [month, year, statusFilter],
  );

  return (
    <div className="space-y-6">
      {/* ── Filters ──────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">
            Mes
          </label>
          <select
            value={month}
            onChange={(e) => setMonth(Number(e.target.value))}
            className="rounded-lg border border-slate-200 bg-white text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {MONTHS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">
            Año
          </label>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="rounded-lg border border-slate-200 bg-white text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {YEARS.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">
            Estado fiscal
          </label>
          <select
            value={statusFilter}
            onChange={(e) =>
              setStatusFilter(e.target.value as TaxStatus | '')
            }
            className="rounded-lg border border-slate-200 bg-white text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ── Download buttons ─────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-3">
        <Button
          variant="outline"
          onClick={() => handleDownload('csv')}
          disabled={downloading !== null}
          className="gap-2"
        >
          {downloading === 'csv' ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FileSpreadsheet className="h-4 w-4" />
          )}
          Exportar CSV
        </Button>
        <Button
          variant="outline"
          onClick={() => handleDownload('zip')}
          disabled={downloading !== null}
          className="gap-2"
        >
          {downloading === 'zip' ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FileArchive className="h-4 w-4" />
          )}
          Exportar documentos (ZIP)
        </Button>
      </div>

      {downloadError && (
        <div className="flex items-center gap-2 text-sm text-rose-600 bg-rose-50 rounded-lg px-4 py-2">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {downloadError}
        </div>
      )}

      {/* ── Monthly report ───────────────────────────────────────────── */}
      {isLoading && (
        <div className="flex justify-center p-8">
          <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
        </div>
      )}

      {isError && (
        <div className="flex items-center gap-2 text-sm text-rose-600 bg-rose-50 rounded-lg px-4 py-3">
          <AlertCircle className="h-4 w-4 shrink-0" />
          Error al cargar el reporte mensual.
        </div>
      )}

      {report && <MonthlyReportView report={report} />}
    </div>
  );
}

// ── Monthly Report Sub-Component ─────────────────────────────────────────────

function MonthlyReportView({ report }: { report: MonthlyReport }) {
  const { profiles, amounts, documents } = report;

  const formatCurrency = (v: string) => {
    const n = parseFloat(v);
    return isNaN(n) ? '$0' : `$${n.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
        <BarChart3 className="h-4 w-4" />
        Reporte mensual
      </div>

      {/* Totals row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Perfiles" value={profiles.total} />
        <StatCard label="Monto total" value={formatCurrency(amounts.total_expense)} />
        <StatCard label="Neto" value={formatCurrency(amounts.total_net)} />
        <StatCard label="IVA" value={formatCurrency(amounts.total_vat)} />
      </div>

      {/* Status breakdown */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        {(Object.entries(TAX_STATUS_CONFIG) as [TaxStatus, typeof TAX_STATUS_CONFIG[TaxStatus]][]).map(
          ([key, cfg]) => (
            <div
              key={key}
              className={cn('rounded-xl border px-3 py-2 text-center', cfg.bg)}
            >
              <div className={cn('text-lg font-bold font-mono', cfg.text)}>
                {profiles.by_status[key] ?? 0}
              </div>
              <div className="text-[11px] text-slate-500">{cfg.label}</div>
            </div>
          ),
        )}
      </div>

      {/* Documents summary */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Documentos totales" value={documents.total} />
        <StatCard
          label="Fiscales"
          value={documents.fiscal}
          className="text-emerald-600"
        />
        <StatCard
          label="No fiscales"
          value={documents.non_fiscal}
          className="text-slate-500"
        />
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  className,
}: {
  label: string;
  value: string | number;
  className?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-center">
      <div className={cn('text-xl font-bold font-mono', className)}>
        {value}
      </div>
      <div className="text-[11px] text-slate-500 mt-0.5">{label}</div>
    </div>
  );
}
