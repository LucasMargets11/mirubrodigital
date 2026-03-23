import { Metadata } from 'next';

import { getAdminDashboardMetrics } from '@/lib/admin';
import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { DashboardContent } from './dashboard-content';

export const metadata: Metadata = {
  title: 'Dashboard | Mi Rubro Admin',
};

export default async function AdminDashboardPage() {
  const metrics = await getAdminDashboardMetrics();

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Dashboard"
        description="Vista general de la plataforma Mi Rubro."
      />

      <DashboardContent metrics={metrics} />
    </div>
  );
}
