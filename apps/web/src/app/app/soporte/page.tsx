import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { getTenantTickets } from './api';
import { SoporteClient } from './soporte-client';

import type { TenantTicketList } from './types';

export default async function SoportePage() {
  const session = await getSession();

  if (!session) {
    redirect('/entrar');
  }

  const role = session.current?.role;
  if (role !== 'owner') {
    return (
      <AccessMessage
        title="Acceso restringido"
        description="Solo el dueño de la cuenta puede acceder al módulo de soporte."
        hint="Pedí acceso al administrador de tu negocio"
      />
    );
  }

  let tickets: TenantTicketList | null = null;
  let fetchError = false;
  try {
    tickets = await getTenantTickets();
  } catch {
    fetchError = true;
  }

  return <SoporteClient initialTickets={tickets} fetchError={fetchError} />;
}
