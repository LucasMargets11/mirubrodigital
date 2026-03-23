import { Metadata } from 'next';

import { getAdminReportingOverview } from '@/lib/admin';
import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { ReportesContent } from './reportes-content';

export const metadata: Metadata = {
  title: 'Reportes | Mi Rubro Admin',
};

export default async function AdminReportesPage() {
  const data = await getAdminReportingOverview();

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Reportes"
        description="Vista 360 de la operación: KPIs, distribuciones, alertas operativas y actividad reciente."
      />

      <ReportesContent data={data} />
    </div>
  );
}
