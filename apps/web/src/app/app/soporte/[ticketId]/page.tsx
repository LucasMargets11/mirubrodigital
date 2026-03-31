import { notFound, redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { getTenantTicketDetail } from '../api';
import { TicketDetailClient } from './ticket-detail-client';

import type { TenantTicketDetail } from '../types';

type PageProps = {
  params: {
    ticketId: string;
  };
};

export default async function TicketDetailPage({ params }: PageProps) {
  const { ticketId } = await params;
  const session = await getSession();

  if (!session) {
    redirect('/entrar');
  }

  const role = session.current?.role;
  if (role !== 'owner') {
    return (
      <AccessMessage
        title="Acceso restringido"
        description="Solo el dueño de la cuenta puede ver tickets de soporte."
        hint="Pedí acceso al administrador de tu negocio"
      />
    );
  }

  let ticket: TenantTicketDetail | null = null;
  try {
    ticket = await getTenantTicketDetail(ticketId);
  } catch {
    notFound();
  }

  if (!ticket) {
    notFound();
  }

  return <TicketDetailClient initialTicket={ticket} />;
}
