import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { PrintablesClient } from './printables-client';

export default async function CartelesPage() {
  const session = await getSession();
  if (!session) {
    redirect('/entrar');
  }

  const featureEnabled = session.features?.print_signage === true;

  if (!featureEnabled) {
    return (
      <AccessMessage
        title="Carteles y Etiquetas está disponible en Gestión Comercial PRO"
        description="Generá carteles de productos en PDF A4, listos para imprimir y recortar."
        hint="Mejorar a PRO"
      />
    );
  }

  return <PrintablesClient />;
}
