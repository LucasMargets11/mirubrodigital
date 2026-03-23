import { Metadata } from 'next';

import { getAdminSubscriptions, getAdminSubscriptionKPIs } from '@/lib/admin';
import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { SuscripcionesContent } from './suscripciones-content';

export const metadata: Metadata = {
  title: 'Suscripciones | Mi Rubro Admin',
};

type Props = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function AdminSuscripcionesPage({ searchParams }: Props) {
  const params = await searchParams;
  const queryParams: Record<string, string> = {};
  for (const [key, val] of Object.entries(params)) {
    if (typeof val === 'string') queryParams[key] = val;
  }

  const [subs, kpis] = await Promise.all([
    getAdminSubscriptions(queryParams),
    getAdminSubscriptionKPIs(),
  ]);

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Suscripciones"
        description="Estado de suscripciones, planes y facturación."
      />
      <SuscripcionesContent
        initialData={subs}
        kpis={kpis}
        initialParams={queryParams}
      />
    </div>
  );
}
