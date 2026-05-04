import { Metadata } from 'next';

import { getAdminPromoCodes } from '@/lib/admin';
import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { PromocionesContent } from './promociones-content';

export const metadata: Metadata = {
  title: 'Promociones | Mi Rubro Admin',
};

type Props = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function AdminPromocionesPage({ searchParams }: Props) {
  const params = await searchParams;
  const queryParams: Record<string, string> = {};
  for (const [key, val] of Object.entries(params)) {
    if (typeof val === 'string') queryParams[key] = val;
  }

  const promos = await getAdminPromoCodes(queryParams);

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Códigos Promocionales"
        description="Gestión de códigos de descuento para suscripciones."
      />
      <PromocionesContent initialData={promos} initialParams={queryParams} />
    </div>
  );
}
