import { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { getAdminTicketDetail, getAdminStaff } from '@/lib/admin';
import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { TicketDetailContent } from './ticket-detail-content';

export const metadata: Metadata = {
  title: 'Detalle de Ticket | Mi Rubro Admin',
};

type Props = {
  params: Promise<{ ticketId: string }>;
};

export default async function AdminTicketDetailPage({ params }: Props) {
  const { ticketId } = await params;

  const [ticket, staff] = await Promise.all([
    getAdminTicketDetail(ticketId),
    getAdminStaff(),
  ]);
  if (!ticket) notFound();

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title={`${ticket.reference} — ${ticket.subject}`}
        description={`Creado ${ticket.created_at ? new Date(ticket.created_at).toLocaleDateString('es-AR') : '—'} · ${ticket.contact_email}`}
      />
      <TicketDetailContent ticket={ticket} staffMembers={staff} />
    </div>
  );
}
