import { TransactionsClient } from './transactions-client';
import { getSession } from '@/lib/auth';
import { listAccounts, listCategories } from '@/lib/api/treasury';

export default async function FinanzasMovimientosPage() {
    const session = await getSession();
    const canManage = session?.permissions?.manage_finance ?? false;

    // Prefetch for filters
    // We could do this client side with react-query too, but layout pattern suggests client usually.
    // I'll stick to client fetching in the Client Component for consistency with AccountsClient.
    
    return <TransactionsClient canManage={canManage} />;
}
