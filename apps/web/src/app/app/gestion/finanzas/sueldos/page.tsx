import { PayrollClient } from './payroll-client';
import { getSession } from '@/lib/auth';

export default async function FinanzasSueldosPage() {
    const session = await getSession();
    const canManage = session?.permissions?.manage_finance ?? false;

    return <PayrollClient canManage={canManage} />;
}
