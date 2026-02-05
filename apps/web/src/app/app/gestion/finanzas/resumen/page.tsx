import { DashboardClient } from './dashboard-client';
import { getSession } from '@/lib/auth';

export default async function FinanzasResumenPage() {
    const session = await getSession();
    const canManage = session?.permissions?.manage_finance ?? false;

    return <DashboardClient canManage={canManage} />;
}
