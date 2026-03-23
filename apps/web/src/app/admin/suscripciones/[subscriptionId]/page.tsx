import { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { getAdminSubscriptionDetail } from '@/lib/admin';
import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { SuscripcionDetailContent } from './suscripcion-detail-content';

export const metadata: Metadata = {
  title: 'Detalle de Suscripción | Mi Rubro Admin',
};

type Props = {
  params: Promise<{ subscriptionId: string }>;
};

export default async function AdminSubscriptionDetailPage({ params }: Props) {
  const { subscriptionId } = await params;
  if (!subscriptionId) notFound();

  const subscription = await getAdminSubscriptionDetail(subscriptionId);
  if (!subscription) notFound();

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title={`Suscripción ${subscription.plan_code?.toUpperCase() ?? '—'}`}
        description={`ID: ${subscription.id} · ${subscription.provider} · ${subscription.business?.name ?? '—'}`}
      />
      <SuscripcionDetailContent subscription={subscription} />
    </div>
  );
}
