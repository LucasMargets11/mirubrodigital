'use client';

import {
  Upload,
  CheckCircle,
  Pencil,
  Replace,
  Clock,
  CreditCard,
  Settings,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { RecommendedAction } from './view-models';

interface RecommendedActionsProps {
  actions: RecommendedAction[];
  onAction: (actionType: RecommendedAction['actionType']) => void;
  className?: string;
}

const ACTION_ICONS: Record<RecommendedAction['actionType'], React.ReactNode> = {
  upload: <Upload className="h-4 w-4" />,
  confirm: <CheckCircle className="h-4 w-4" />,
  edit: <Pencil className="h-4 w-4" />,
  replace: <Replace className="h-4 w-4" />,
  defer: <Clock className="h-4 w-4" />,
  payment: <CreditCard className="h-4 w-4" />,
  technical: <Settings className="h-4 w-4" />,
};

export function RecommendedActions({ actions, onAction, className }: RecommendedActionsProps) {
  if (actions.length === 0) return null;

  return (
    <div className={cn('rounded-xl border border-slate-200 bg-white', className)}>
      <div className="px-5 pt-4 pb-2">
        <h4 className="text-sm font-bold text-slate-800">
          Acciones recomendadas
        </h4>
      </div>
      <div className="px-5 pb-4 space-y-2">
        {actions.map((action) => (
          <button
            key={action.key}
            onClick={() => onAction(action.actionType)}
            className={cn(
              'w-full flex items-center gap-3 p-3 rounded-lg text-left transition-all focus:outline-none focus:ring-2 focus:ring-offset-1',
              action.variant === 'primary' &&
                'bg-indigo-600 text-white hover:bg-indigo-700 focus:ring-indigo-500',
              action.variant === 'secondary' &&
                'bg-slate-100 text-slate-800 hover:bg-slate-200 focus:ring-slate-400',
              action.variant === 'outline' &&
                'border border-slate-200 text-slate-700 hover:bg-slate-50 focus:ring-slate-300',
            )}
          >
            <div className={cn(
              'p-2 rounded-lg shrink-0',
              action.variant === 'primary' && 'bg-indigo-500',
              action.variant === 'secondary' && 'bg-slate-200',
              action.variant === 'outline' && 'bg-slate-100',
            )}>
              {ACTION_ICONS[action.actionType]}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold">{action.label}</p>
              <p className={cn(
                'text-xs mt-0.5',
                action.variant === 'primary' ? 'text-indigo-200' : 'text-slate-500',
              )}>
                {action.description}
              </p>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
