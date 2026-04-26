import { redirect } from 'next/navigation';
import { getSession } from '@/lib/auth';
import { ReponerClient } from './reponer-client';

export default async function ReponerPage() {
    const session = await getSession();

    if (!session) redirect('/login' as any);

    const canManage = session.permissions?.manage_purchases ?? false;
    if (!canManage) redirect('/app/gestion/stock/compras' as any);

    return (
        <div className="p-4 md:p-8">
            <ReponerClient />
        </div>
    );
}
