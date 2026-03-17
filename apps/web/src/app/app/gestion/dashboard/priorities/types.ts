import type { LucideIcon } from 'lucide-react';

export type PrioritySeverity = 'critical' | 'urgent' | 'important' | 'informative';

export type DailyPriority = {
    id: string;
    title: string;
    severity: PrioritySeverity;
    href: string;
    actionLabel: string;
    icon: LucideIcon;
    count?: number;
    amount?: number;
};

export const SEVERITY_ORDER: Record<PrioritySeverity, number> = {
    critical: 0,
    urgent: 1,
    important: 2,
    informative: 3,
};
