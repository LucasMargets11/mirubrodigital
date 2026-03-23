import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { EmptyState } from '@/components/admin/empty-state';
import { Users } from 'lucide-react';

export const metadata = {
  title: 'Clientes | Mi Rubro Admin',
};

export default function AdminClientesPage() {
  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Clientes"
        description="Gestión de negocios registrados en la plataforma."
      />

      <EmptyState
        icon={<Users className="h-12 w-12" />}
        title="Módulo de clientes"
        description="Próximamente podrás ver, buscar y gestionar todos los negocios registrados en Mi Rubro desde aquí."
      />
    </div>
  );
}
