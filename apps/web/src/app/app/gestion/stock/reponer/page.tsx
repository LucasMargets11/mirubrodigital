import { redirect } from 'next/navigation';
import { getSession } from '@/lib/auth';
import { ReponerClient } from './reponer-client';

export default async function ReponerPage() {
    const session = await getSession();

    if (!session) redirect('/login');

    const canManage = session.permissions?.manage_purchases ?? false;
    if (!canManage) redirect('/app/gestion/stock/compras');

    return (
        <div className="p-4 md:p-8">
            <ReponerClient />
        </div>
    );
}
