import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { EmptyState } from '@/components/admin/empty-state';
import { HeadphonesIcon } from 'lucide-react';

export const metadata = {
  title: 'Soporte | Mi Rubro Admin',
};

export default function AdminSoportePage() {
  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Soporte"
        description="Tickets y solicitudes de soporte de los clientes."
      />

      <EmptyState
        icon={<HeadphonesIcon className="h-12 w-12" />}
        title="Módulo de soporte"
        description="Próximamente podrás gestionar tickets de soporte, responder consultas y hacer seguimiento de solicitudes desde aquí."
      />
    </div>
  );
}
