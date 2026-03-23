import { Metadata } from 'next';

import { getAdminClients, getAdminClientKPIs } from '@/lib/admin';
import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { ClientesContent } from './clientes-content';

export const metadata: Metadata = {
  title: 'Clientes | Mi Rubro Admin',
};

type Props = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function AdminClientesPage({ searchParams }: Props) {
  const params = await searchParams;
  const queryParams: Record<string, string> = {};
  for (const [key, val] of Object.entries(params)) {
    if (typeof val === 'string') queryParams[key] = val;
  }

  const [clients, kpis] = await Promise.all([
    getAdminClients(queryParams),
    getAdminClientKPIs(),
  ]);

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Clientes"
        description="Negocios registrados en la plataforma."
      />
      <ClientesContent
        initialData={clients}
        kpis={kpis}
        initialParams={queryParams}
      />
    </div>
  );
}
