"use client";

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Loader2, Plus, Eye } from 'lucide-react';

import {
  getProfileSummary,
  taxBackupKeys,
  type TaxBackupSummary,
} from '@/lib/api/tax-backup';
import { listExpenses, type Expense } from '@/lib/api/treasury';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import { TaxBackupDashboard } from './tax-backup-dashboard';
import { TaxBackupTable } from './tax-backup-table';
import { TaxBackupExports } from './tax-backup-exports';
import { TaxBackupChecklist } from './tax-backup-checklist';
import { CreateProfileModal } from './create-profile-modal';

type MainTab = 'profiles' | 'exports' | 'checklist';

export function TaxBackupClient({ canManage }: { canManage: boolean }) {
  const router = useRouter();
  const [mainTab, setMainTab] = useState<MainTab>('profiles');
  const [showCreate, setShowCreate] = useState(false);

  // Summary for dashboard cards
  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: taxBackupKeys.summary(),
    queryFn: getProfileSummary,
  });

  // Expenses without fiscal profile (for create modal)
  const { data: expensesData } = useQuery({
    queryKey: ['treasury', 'expenses', 'all-for-tax-backup'],
    queryFn: () => listExpenses({ limit: 500 }),
  });

  // Filter expenses that don't already have a fiscal_profile
  const availableExpenses: Expense[] = (expensesData?.results ?? []).filter(
    (e: any) => !e.fiscal_profile,
  );

  /** Navigate to the dedicated review workspace */
  const handleReview = (profileId: number) => {
    router.push(`/app/gestion/finanzas/gastos/respaldo/${profileId}` as any);
  };

  return (
    <div className="space-y-6">
      {/* Read-only banner */}
      {!canManage && (
        <div className="flex items-center gap-2 p-3 bg-sky-50 border border-sky-200 rounded-lg text-sm text-sky-800">
          <Eye className="h-4 w-4 shrink-0" />
          <span>Vista de solo lectura — podés consultar y exportar, pero no modificar datos.</span>
        </div>
      )}

      {/* Dashboard summary */}
      {summaryLoading ? (
        <div className="flex justify-center p-6">
          <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
        </div>
      ) : summary ? (
        <TaxBackupDashboard summary={summary as TaxBackupSummary} />
      ) : null}

      {/* Main tab switcher + create button */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
        <div className="flex gap-1 p-1 bg-slate-100 rounded-xl w-fit">
          <button
            onClick={() => setMainTab('profiles')}
            className={cn(
              'px-5 py-2 text-sm font-medium rounded-lg transition-all',
              mainTab === 'profiles'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-900',
            )}
          >
            Perfiles
          </button>
          <button
            onClick={() => setMainTab('exports')}
            className={cn(
              'px-5 py-2 text-sm font-medium rounded-lg transition-all',
              mainTab === 'exports'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-900',
            )}
          >
            Exportes
          </button>
          <button
            onClick={() => setMainTab('checklist')}
            className={cn(
              'px-5 py-2 text-sm font-medium rounded-lg transition-all',
              mainTab === 'checklist'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-900',
            )}
          >
            Checklist
          </button>
        </div>

        {mainTab === 'profiles' && canManage && (
          <Button
            onClick={() => setShowCreate(true)}
            className="rounded-full w-full md:w-auto"
          >
            <Plus className="mr-2 h-4 w-4" />
            Nuevo perfil
          </Button>
        )}
      </div>

      {/* Main content — inbox-style table (no inline detail panel) */}
      {mainTab === 'profiles' && (
        <TaxBackupTable
          selectedId={null}
          onSelect={handleReview}
          compact={false}
        />
      )}

      {mainTab === 'exports' && <TaxBackupExports />}

      {mainTab === 'checklist' && <TaxBackupChecklist />}

      {/* Create modal */}
      {canManage && showCreate && (
        <CreateProfileModal
          isOpen={showCreate}
          onClose={() => setShowCreate(false)}
          availableExpenses={availableExpenses}
        />
      )}
    </div>
  );
}
