import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { EmptyState } from '@/components/admin/empty-state';
import { Settings } from 'lucide-react';

export const metadata = {
  title: 'Configuración | Mi Rubro Admin',
};

export default function AdminConfiguracionPage() {
  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Configuración"
        description="Ajustes globales de la plataforma, feature flags y configuración interna."
      />

      <EmptyState
        icon={<Settings className="h-12 w-12" />}
        title="Módulo de configuración"
        description="Próximamente podrás gestionar ajustes globales, feature flags, roles internos y configuración de la plataforma desde aquí."
      />
    </div>
  );
}
