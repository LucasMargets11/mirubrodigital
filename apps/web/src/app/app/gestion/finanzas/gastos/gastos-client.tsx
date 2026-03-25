"use client";

import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import { FixedExpensesClient } from './fixed-expenses-client';
import { PunctualExpensesClient } from './expenses-client';
import { ReplenishmentExpensesClient } from './replenishment-expenses-client';
import { TaxBackupClient } from './tax-backup/tax-backup-client';
import { EntitlementGate } from '@/components/gestion/entitlement-gate';
import { SectionViewSwitcher, type SectionView } from '@/components/navigation/section-view-switcher';

type GastosTab = 'fijos' | 'puntuales' | 'reposiciones' | 'respaldo';

const GASTOS_VIEWS: SectionView[] = [
    { key: 'fijos', label: 'Gastos Fijos' },
    { key: 'puntuales', label: 'Gastos Puntuales' },
    { key: 'reposiciones', label: 'Reposiciones de Stock' },
    { key: 'respaldo', label: 'Respaldo Impositivo' },
];

export function GastosClient({ canManage }: { canManage: boolean }) {
    const searchParams = useSearchParams();
    const router = useRouter();
    const pathname = usePathname();

    const activeTab: GastosTab = (searchParams.get('tab') as GastosTab) || 'fijos';

    const setTab = (tab: string) => {
        const params = new URLSearchParams(searchParams.toString());
        params.set('tab', tab);
        router.replace(`${pathname}?${params.toString()}` as any);
    };

    return (
        <div className="space-y-6">
            <SectionViewSwitcher
                views={GASTOS_VIEWS}
                activeKey={activeTab}
                onChange={setTab}
                ariaLabel="Tipo de gasto"
            />

            {/* Content */}
            {activeTab === 'fijos' ? (
                <FixedExpensesClient canManage={canManage} />
            ) : activeTab === 'reposiciones' ? (
                <ReplenishmentExpensesClient />
            ) : activeTab === 'respaldo' ? (
                <EntitlementGate
                    entitlement="gestion.tax_backup"
                    feature="Respaldo Impositivo"
                    plan="Gestión Business"
                    description="Organizá y respaldá la documentación fiscal de tus gastos."
                >
                    <TaxBackupClient canManage={canManage} />
                </EntitlementGate>
            ) : (
                <PunctualExpensesClient canManage={canManage} />
            )}
        </div>
    );
}
