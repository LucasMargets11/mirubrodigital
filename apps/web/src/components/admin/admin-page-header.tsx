"use client";

import { ReactNode } from 'react';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { cn } from '@/lib/utils';

type AdminPageHeaderProps = {
  title: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
  backHref?: string;
  backLabel?: string;
};

export function AdminPageHeader({ title, description, actions, className, backHref, backLabel }: AdminPageHeaderProps) {
  return (
    <div className={cn('space-y-1', className)}>
      {backHref && (
        <Link
          href={backHref as any}
          className="mb-2 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"
        >
          <ArrowLeft className="h-4 w-4" />
          {backLabel ?? 'Volver'}
        </Link>
      )}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
          {description && (
            <p className="mt-1 text-sm text-slate-500">{description}</p>
          )}
        </div>
        {actions && (
          <div className="flex items-center gap-2 shrink-0">{actions}</div>
        )}
      </div>
    </div>
  );
}
