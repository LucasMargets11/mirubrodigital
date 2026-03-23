import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

import { PlanBillingClient } from './plan-billing-client';

export default async function PlanFacturacionPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    return <PlanBillingClient session={session} />;
}
