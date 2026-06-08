import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { serverApiFetch } from '@/lib/api/server';
import type { PublicMenuConfig } from '@/features/menu/types';

import { RestoHomeClient } from './resto-home-client';

export default async function RestoHomePage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    if (session.current.service !== 'restaurante') {
        redirect('/app/servicios');
    }

    // Best-effort: published state for the public menu. Never block the dashboard.
    let menuConfig: PublicMenuConfig | null = null;
    try {
        menuConfig = await serverApiFetch<PublicMenuConfig>('/api/v1/menu/public/config/');
    } catch {
        menuConfig = null;
    }

    return (
        <RestoHomeClient
            businessName={session.current.business.name}
            businessStatus={session.current.business.status}
            planName={session.subscription.plan}
            permissions={{
                canViewOrders: session.permissions?.view_orders ?? false,
                canViewKitchen: session.permissions?.view_kitchen_board ?? false,
                canViewCash: session.permissions?.view_cash ?? false,
                canViewMenu: session.permissions?.view_menu ?? false,
                canManageReviews: session.permissions?.manage_reviews ?? false,
                canManageSettings: session.permissions?.manage_settings ?? false,
                canViewReports: session.permissions?.view_restaurant_reports ?? false,
            }}
            features={{
                orders: session.features?.resto_orders !== false,
                kitchen: session.features?.resto_kitchen !== false,
                menu: session.features?.resto_menu !== false,
                cash: session.features?.cash !== false,
                reviews: session.features?.qr_reviews_core === true,
                reports: session.features?.resto_reports === true,
            }}
            menuPublished={menuConfig?.enabled ?? null}
        />
    );
}
