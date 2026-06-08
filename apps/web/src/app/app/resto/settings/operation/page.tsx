import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { RestaurantOperationSettingsForm } from '@/features/resto/components/restaurant-operation-settings-form';
import { getSession } from '@/lib/auth';

export default async function RestaurantOperationSettingsPage() {
  const session = await getSession();

  if (!session) {
    redirect('/entrar');
  }

  const featureEnabled = session.features?.settings !== false;
  const canManage = session.permissions?.manage_tables ?? false;

  if (!featureEnabled) {
    return (
      <AccessMessage
        title="Tu plan no incluye configuracion"
        description="Actualiza tu plan para habilitar configuraciones avanzadas de restaurante."
      />
    );
  }

  if (!canManage) {
    return (
      <AccessMessage
        title="Sin acceso"
        description="Tu rol no tiene permiso para editar la operacion del restaurante."
        hint="Pedi acceso a un administrador"
      />
    );
  }

  return <RestaurantOperationSettingsForm />;
}
