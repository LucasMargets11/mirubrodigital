import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { NuevoTicketClient } from './nuevo-ticket-client';

export default async function NuevoTicketPage() {
  const session = await getSession();

  if (!session) {
    redirect('/entrar');
  }

  const role = session.current?.role;
  if (role !== 'owner') {
    return (
      <AccessMessage
        title="Acceso restringido"
        description="Solo el dueño de la cuenta puede crear tickets de soporte."
        hint="Pedí acceso al administrador de tu negocio"
      />
    );
  }

  return <NuevoTicketClient />;
}
