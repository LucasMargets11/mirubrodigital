import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { ReviewsDashboardClient } from './dashboard-client';

export default async function ResenasPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    return <ReviewsDashboardClient />;
}
