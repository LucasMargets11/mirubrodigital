import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

import { EngagementPageClient } from './engagement-client';

export default async function EngagementPage() {
    const session = await getSession();
    if (!session) redirect('/entrar');

    const canView = session.permissions?.view_menu ?? false;
    if (!canView) redirect('/app/servicios');

    return <EngagementPageClient />;
}
