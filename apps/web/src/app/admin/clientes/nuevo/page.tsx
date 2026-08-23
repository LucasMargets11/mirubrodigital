import { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { getAdminSession } from '@/lib/admin';
import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { NuevoClienteForm } from './nuevo-cliente-form';

export const metadata: Metadata = {
  title: 'Nuevo cliente | Mi Rubro Admin',
};

/**
 * /admin/clientes/nuevo — superadmin-only. Resolved server-side (before any
 * client render) so an unauthorized role never sees the form flash on
 * screen while the session resolves.
 */
export default async function AdminClienteNuevoPage() {
  const session = await getAdminSession();
  if (!session) {
    redirect('/admin/login');
  }
  if (session.internal_role !== 'superadmin') {
    redirect('/admin/clientes');
  }

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Nuevo cliente"
        description="Creá el negocio, su owner y una suscripción bonificada desde el panel administrativo."
        backHref="/admin/clientes"
        backLabel="Volver a Clientes"
      />
      <NuevoClienteForm />
    </div>
  );
}
