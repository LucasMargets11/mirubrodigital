"use client";

import { cn } from '@/lib/utils';
import { Loader2 } from 'lucide-react';

type LoadingStateProps = {
  message?: string;
  className?: string;
};

export function LoadingState({ message = 'Cargando...', className }: LoadingStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center rounded-xl border border-slate-200 bg-white px-6 py-16 text-center',
        className,
      )}
    >
      <Loader2 className="mb-3 h-8 w-8 animate-spin text-brand-500" />
      <p className="text-sm text-slate-500">{message}</p>
    </div>
  );
}
