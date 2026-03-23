import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { EmptyState } from '@/components/admin/empty-state';
import { BarChart3 } from 'lucide-react';

export const metadata = {
  title: 'Reportes | Mi Rubro Admin',
};

export default function AdminReportesPage() {
  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Reportes"
        description="Métricas globales, uso de la plataforma y análisis de rendimiento."
      />

      <EmptyState
        icon={<BarChart3 className="h-12 w-12" />}
        title="Módulo de reportes"
        description="Próximamente podrás consultar métricas de uso, crecimiento, retención y rendimiento de la plataforma desde aquí."
      />
    </div>
  );
}
