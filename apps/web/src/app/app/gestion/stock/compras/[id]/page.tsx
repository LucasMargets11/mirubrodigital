import { redirect } from 'next/navigation';
import { getSession } from '@/lib/auth';
import { StockNav } from '@/app/app/gestion/stock/stock-nav';
import { ReplenishmentDetailClient } from './replenishment-detail-client';

interface Props {
    params: Promise<{ id: string }>;
}

export default async function ComprasDetailPage({ params }: Props) {
    const { id } = await params;
    const session = await getSession();

    if (!session) redirect('/login');

    const canView = session.permissions?.view_purchases ?? false;
    if (!canView) redirect('/app/gestion/stock/compras');

    const canManage = session.permissions?.manage_purchases ?? false;

    return (
        <div>
            <StockNav />
            <div className="p-4 md:p-8">
                <ReplenishmentDetailClient id={id} canManage={canManage} />
            </div>
        </div>
    );
}
