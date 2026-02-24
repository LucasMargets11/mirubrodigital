"use client";

import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { FixedExpensesClient } from './fixed-expenses-client';
import { PunctualExpensesClient } from './expenses-client';
import { ReplenishmentExpensesClient } from './replenishment-expenses-client';

type GastosTab = 'fijos' | 'puntuales' | 'reposiciones';

export function GastosClient({ canManage }: { canManage: boolean }) {
    const searchParams = useSearchParams();
    const router = useRouter();
    const pathname = usePathname();

    const activeTab: GastosTab = (searchParams.get('tab') as GastosTab) || 'fijos';

    const setTab = (tab: GastosTab) => {
        const params = new URLSearchParams(searchParams.toString());
        params.set('tab', tab);
        router.replace(`${pathname}?${params.toString()}` as any);
    };

    return (
        <div className="space-y-6">
            {/* Tab switcher */}
            <div className="flex gap-1 p-1 bg-slate-100 rounded-xl w-fit">
                <button
                    onClick={() => setTab('fijos')}
                    className={cn(
                        'px-5 py-2 text-sm font-medium rounded-lg transition-all',
                        activeTab === 'fijos'
                            ? 'bg-white text-slate-900 shadow-sm'
                            : 'text-slate-500 hover:text-slate-900'
                    )}
                >
                    Gastos Fijos
                </button>
                <button
                    onClick={() => setTab('puntuales')}
                    className={cn(
                        'px-5 py-2 text-sm font-medium rounded-lg transition-all',
                        activeTab === 'puntuales'
                            ? 'bg-white text-slate-900 shadow-sm'
                            : 'text-slate-500 hover:text-slate-900'
                    )}
                >
                    Gastos Puntuales
                </button>
                <button
                    onClick={() => setTab('reposiciones')}
                    className={cn(
                        'px-5 py-2 text-sm font-medium rounded-lg transition-all',
                        activeTab === 'reposiciones'
                            ? 'bg-white text-violet-700 shadow-sm'
                            : 'text-slate-500 hover:text-slate-900'
                    )}
                >
                    Reposiciones de Stock
                </button>
            </div>

            {/* Content */}
            {activeTab === 'fijos' ? (
                <FixedExpensesClient canManage={canManage} />
            ) : activeTab === 'reposiciones' ? (
                <ReplenishmentExpensesClient />
            ) : (
                <PunctualExpensesClient canManage={canManage} />
            )}
        </div>
    );
}
