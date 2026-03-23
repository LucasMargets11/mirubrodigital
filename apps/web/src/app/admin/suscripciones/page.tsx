import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { EmptyState } from '@/components/admin/empty-state';
import { CreditCard } from 'lucide-react';

export const metadata = {
  title: 'Suscripciones | Mi Rubro Admin',
};

export default function AdminSuscripcionesPage() {
  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Suscripciones"
        description="Estado de suscripciones, planes y facturación de la plataforma."
      />

      <EmptyState
        icon={<CreditCard className="h-12 w-12" />}
        title="Módulo de suscripciones"
        description="Próximamente podrás gestionar planes, ver estado de pagos y administrar la facturación desde aquí."
      />
    </div>
  );
}
