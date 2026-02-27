import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { serverApiFetch } from '@/lib/api/server';
import type { CommercialSubscription } from '@/types/billing';
import { BillingPageClient } from '@/components/gestion/billing-page-client';
import { MenuQrBillingView } from '@/components/app/menu-qr-billing-view';

export default async function BillingHubPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const service = session.current?.service ?? 'gestion';

    // Non-commercial services (menu_qr, restaurante) don't use the commercial subscription endpoint
    if (service !== 'gestion') {
        return (
            <MenuQrBillingView
                service={service}
                plan={session.subscription?.plan ?? ''}
                status={session.subscription?.status ?? 'active'}
                businessName={session.current?.business?.name ?? ''}
            />
        );
    }

    let subscription: CommercialSubscription | null = null;
    try {
        subscription = await serverApiFetch<CommercialSubscription>('/api/v1/billing/commercial/subscription/');
    } catch (error) {
        console.error('Failed to fetch commercial subscription:', error);
    }

    if (!subscription) {
        return (
            <section className="space-y-4">
                <header>
                    <p className="text-xs uppercase tracking-wide text-slate-400">Gestión Comercial</p>
                    <h1 className="text-3xl font-semibold text-slate-900">Plan y Facturación</h1>
                    <p className="text-sm text-slate-500">No pudimos cargar la información. Reintentá en unos segundos.</p>
                </header>
            </section>
        );
    }

    return <BillingPageClient subscription={subscription} />;
}
