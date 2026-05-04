"use client";

import { useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { getPublicApiBaseUrl } from '@/lib/api-url';

import { DataTable, type DataTableColumn } from '@/components/admin/data-table';
import { StatusBadge } from '@/components/admin/status-badge';
import { SectionCard } from '@/components/admin/section-card';
import { Pagination } from '@/components/admin/pagination';
import { formatDate, formatDateTime } from '@/lib/admin/display';
import type { AdminPromoCodeRow, AdminPromoCodeRedemptionRow, AdminPromoCodeRedemptionList } from '@/lib/admin/types';

type Props = {
  promo: AdminPromoCodeRow;
  initialRedemptions: AdminPromoCodeRedemptionList | null;
  promoId: number;
};

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-800',
  completed: 'bg-blue-100 text-blue-800',
  cancelled: 'bg-red-100 text-red-600',
  expired: 'bg-slate-100 text-slate-500',
  pending: 'bg-yellow-100 text-yellow-800',
};

const REDEMPTION_COLUMNS: DataTableColumn<AdminPromoCodeRedemptionRow>[] = [
  {
    key: 'business_name',
    header: 'Negocio',
    render: (r) => <span className="text-sm">{r.business_name ?? `#${r.business_id}`}</span>,
  },
  {
    key: 'user_email',
    header: 'Usuario',
    render: (r) => <span className="text-sm text-slate-500">{r.user_email ?? '—'}</span>,
  },
  {
    key: 'status',
    header: 'Estado',
    render: (r) => (
      <StatusBadge
        label={r.status}
        colorClass={STATUS_COLORS[r.status] ?? 'bg-slate-100 text-slate-600'}
      />
    ),
  },
  {
    key: 'cycles_used',
    header: 'Ciclos',
    className: 'text-center',
    render: (r) => (
      <span className="text-sm">{r.cycles_used} / {r.cycles_total}</span>
    ),
  },
  {
    key: 'discounted_amount',
    header: 'Descuento',
    render: (r) => (
      <span className="text-sm">${r.discounted_amount}</span>
    ),
  },
  {
    key: 'price_restored',
    header: 'Precio restaurado',
    render: (r) => (
      <span className="text-sm">{r.price_restored ? (r.price_restored_at ? formatDate(r.price_restored_at) : 'Sí') : 'No'}</span>
    ),
  },
  {
    key: 'created_at',
    header: 'Fecha',
    render: (r) => <span className="text-sm text-slate-500">{r.created_at ? formatDate(r.created_at) : '—'}</span>,
  },
];

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between py-2 text-sm border-b border-slate-100 last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium text-slate-800">{value}</span>
    </div>
  );
}

export function PromoDetailContent({ promo, initialRedemptions, promoId }: Props) {
  const router = useRouter();
  const API_URL = getPublicApiBaseUrl();
  const [isPending, startTransition] = useTransition();
  const [deactivated, setDeactivated] = useState(!promo.active);
  const [deactivateError, setDeactivateError] = useState('');
  const [redeemPage, setRedeemPage] = useState(initialRedemptions?.page ?? 1);

  const totalPages = initialRedemptions?.total_pages ?? 1;

  function handleDeactivate() {
    if (!confirm('¿Desactivar este código? Los canjes activos seguirán su ciclo normalmente.')) return;
    startTransition(async () => {
      setDeactivateError('');
      try {
        const resp = await fetch(`${API_URL}/api/v1/platform-admin/promo-codes/${promoId}/`, {
          method: 'PATCH',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ active: false }),
        });
        if (resp.ok) {
          setDeactivated(true);
        } else {
          setDeactivateError('No se pudo desactivar el código. Intentá de nuevo.');
        }
      } catch {
        setDeactivateError('Error de red.');
      }
    });
  }

  function handleRedemptionPage(page: number) {
    setRedeemPage(page);
    router.push(`/admin/promociones/${promoId}?page=${page}`);
  }

  const discountLabel =
    promo.discount_type === 'percent' ? `${promo.discount_value}%` : `$${promo.discount_value}`;

  return (
    <div className="space-y-6">
      {/* Info card */}
      <SectionCard title="Información del código">
        <div className="divide-y divide-slate-100">
          <InfoRow label="Código" value={<span className="font-mono">{promo.code}</span>} />
          <InfoRow label="Nombre" value={promo.name} />
          {promo.description && <InfoRow label="Descripción" value={promo.description} />}
          <InfoRow label="Descuento" value={discountLabel} />
          <InfoRow label="Ciclos" value={promo.duration_cycles} />
          <InfoRow label="Planes" value={promo.applies_to_plan_codes.join(', ')} />
          <InfoRow label="Períodos" value={promo.applies_to_billing_periods.join(', ')} />
          <InfoRow label="Usos activos" value={`${promo.redemptions_count}${promo.max_redemptions !== null ? ` / ${promo.max_redemptions}` : ''}`} />
          <InfoRow label="Límite por negocio" value={promo.max_redemptions_per_business} />
          <InfoRow label="Válido desde" value={promo.starts_at ? formatDateTime(promo.starts_at) : '—'} />
          <InfoRow label="Válido hasta" value={promo.ends_at ? formatDateTime(promo.ends_at) : '—'} />
          <InfoRow label="Creado por" value={promo.created_by_email ?? '—'} />
          <InfoRow label="Creado" value={promo.created_at ? formatDateTime(promo.created_at) : '—'} />
          <InfoRow
            label="Estado"
            value={
              <StatusBadge
                label={deactivated ? 'Inactivo' : 'Activo'}
                colorClass={deactivated ? 'bg-slate-100 text-slate-500' : 'bg-green-100 text-green-800'}
              />
            }
          />
        </div>

        {!deactivated && (
          <div className="mt-4 flex items-center gap-4">
            <button
              onClick={handleDeactivate}
              disabled={isPending}
              className="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-60"
            >
              {isPending ? 'Desactivando...' : 'Desactivar código'}
            </button>
            {deactivateError && (
              <span className="text-sm text-red-600">{deactivateError}</span>
            )}
          </div>
        )}
      </SectionCard>

      {/* Redemptions */}
      <SectionCard title={`Canjes (${initialRedemptions?.total ?? 0})`}>
        {initialRedemptions && initialRedemptions.results.length > 0 ? (
          <>
            <DataTable
              columns={REDEMPTION_COLUMNS}
              data={initialRedemptions.results}
              keyExtractor={(r) => r.id}
            />
            <div className="mt-4">
              <Pagination
                page={redeemPage}
                totalPages={totalPages}
                onPageChange={handleRedemptionPage}
              />
            </div>
          </>
        ) : (
          <p className="py-6 text-center text-sm text-slate-500">Sin canjes registrados.</p>
        )}
      </SectionCard>
    </div>
  );
}
