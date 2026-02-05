import { AccountsClient } from './accounts-client';
import { getSession } from '@/lib/auth';

export default async function FinanzasCuentasPage() {
    const session = await getSession();
    const canManage = session?.permissions?.manage_finance ?? false;

    return <AccountsClient canManage={canManage} />;
}
