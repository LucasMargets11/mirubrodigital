import { redirect } from 'next/navigation';
import { getSession } from '@/lib/auth';
import { StockNav } from '@/app/app/gestion/stock/stock-nav';
import { ReponerClient } from './reponer-client';

export default async function ReponerPage() {
    const session = await getSession();

    if (!session) redirect('/login');

    const canManage = session.permissions?.manage_purchases ?? false;
    if (!canManage) redirect('/app/gestion/stock/compras');

    return (
        <div>
            <StockNav />
            <div className="p-4 md:p-8">
                <ReponerClient />
            </div>
        </div>
    );
}
