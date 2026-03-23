"use client";

import { cn } from '@/lib/utils';

type StatusBadgeProps = {
  label: string;
  colorClass: string;
  className?: string;
};

export function StatusBadge({ label, colorClass, className }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        colorClass,
        className,
      )}
    >
      {label}
    </span>
  );
}
