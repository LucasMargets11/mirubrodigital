import { ExpensesClient } from './expenses-client';
import { getSession } from '@/lib/auth';

export default async function FinanzasGastosPage() {
    const session = await getSession();
    const canManage = session?.permissions?.manage_finance ?? false;

    return <ExpensesClient canManage={canManage} />;
}
