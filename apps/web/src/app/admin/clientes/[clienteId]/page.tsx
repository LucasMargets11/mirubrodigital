import { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { getAdminClientDetail } from '@/lib/admin';
import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { ClienteDetailContent } from './cliente-detail-content';

export const metadata: Metadata = {
  title: 'Detalle de Cliente | Mi Rubro Admin',
};

type Props = {
  params: Promise<{ clienteId: string }>;
};

export default async function AdminClienteDetailPage({ params }: Props) {
  const { clienteId } = await params;
  const id = parseInt(clienteId, 10);
  if (isNaN(id)) notFound();

  const client = await getAdminClientDetail(id);
  if (!client) notFound();

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title={client.name}
        description={`ID: ${client.id} · ${client.service_type || '—'} · ${client.country}`}
      />
      <ClienteDetailContent client={client} />
    </div>
  );
}
