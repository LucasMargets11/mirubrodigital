"use client";

import { cn } from '@/lib/utils';
import { AlertTriangle } from 'lucide-react';

type ErrorStateProps = {
  title?: string;
  message?: string;
  retry?: () => void;
  className?: string;
};

export function ErrorState({
  title = 'Algo salió mal',
  message = 'No pudimos cargar la información. Intentá de nuevo más tarde.',
  retry,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center rounded-xl border border-red-200 bg-red-50 px-6 py-12 text-center',
        className,
      )}
    >
      <AlertTriangle className="mb-3 h-8 w-8 text-red-400" />
      <h3 className="text-lg font-semibold text-red-900">{title}</h3>
      <p className="mt-1 max-w-sm text-sm text-red-600">{message}</p>
      {retry && (
        <button
          type="button"
          onClick={retry}
          className="mt-4 rounded-md bg-red-100 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-200 transition-colors"
        >
          Reintentar
        </button>
      )}
    </div>
  );
}
