import { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { getAdminPromoCodeDetail, getAdminPromoCodeRedemptions } from '@/lib/admin';
import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { PromoDetailContent } from './promo-detail-content';

export const metadata: Metadata = {
  title: 'Detalle Código Promocional | Mi Rubro Admin',
};

type Props = {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function AdminPromoDetailPage({ params, searchParams }: Props) {
  const { id } = await params;
  const numId = parseInt(id, 10);
  if (isNaN(numId)) notFound();

  const sp = await searchParams;
  const queryParams: Record<string, string> = {};
  for (const [key, val] of Object.entries(sp)) {
    if (typeof val === 'string') queryParams[key] = val;
  }

  const [promo, redemptions] = await Promise.all([
    getAdminPromoCodeDetail(numId),
    getAdminPromoCodeRedemptions(numId, queryParams),
  ]);

  if (!promo) notFound();

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title={`Código: ${promo.code}`}
        description={promo.name}
      />
      <PromoDetailContent promo={promo} initialRedemptions={redemptions} promoId={numId} />
    </div>
  );
}
