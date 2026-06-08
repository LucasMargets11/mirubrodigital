import Link from 'next/link';
import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

export default async function RestaurantSettingsIndexPage() {
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
        description="Tu rol no tiene permiso para editar la configuracion del restaurante."
        hint="Pedi acceso a un administrador"
      />
    );
  }

  return (
    <section className="space-y-6">
      <header className="space-y-2">
        <p className="text-xs uppercase tracking-wide text-slate-400">Restaurante inteligente</p>
        <h1 className="text-3xl font-semibold text-slate-900">Configuracion</h1>
        <p className="text-sm text-slate-500">Administra mesas y operacion del restaurante desde una sola vista.</p>
      </header>

      <div className="grid gap-4 md:grid-cols-2">
        <Link
          href="/app/resto/settings/operation"
          className="group rounded-xl border border-slate-200 bg-white p-6 transition-all hover:border-blue-300 hover:shadow-md"
        >
          <h3 className="text-base font-semibold text-slate-900 group-hover:text-blue-700">Operacion del restaurante</h3>
          <p className="mt-2 text-sm text-slate-500">
            Configura cocina, mesas, canales y modo por defecto del POS.
          </p>
        </Link>

        <Link
          href="/app/resto/settings/tables"
          className="group rounded-xl border border-slate-200 bg-white p-6 transition-all hover:border-blue-300 hover:shadow-md"
        >
          <h3 className="text-base font-semibold text-slate-900 group-hover:text-blue-700">Configurar mesas</h3>
          <p className="mt-2 text-sm text-slate-500">
            Edita layout, disponibilidad y distribucion del salon.
          </p>
        </Link>
      </div>
    </section>
  );
}
