'use client';

import { cn } from '@/lib/utils';

import type { SetupSection, SetupStep, StepStatusMap, UpgradeNudge } from '../types';
import { computeProgress } from '../use-gestion-help';
import { UpgradeNudgeBlock } from './upgrade-nudge-block';

// ─── Individual step row ──────────────────────────────────────────────

interface StepRowProps {
    step: SetupStep;
    status: 'pending' | 'completed';
    onNavigate?: (href: string) => void;
}

function StepRow({ step, status, onNavigate }: StepRowProps) {
    const done = status === 'completed';
    const isProducts = step.id === 'gestion.products';

    return (
        <div
            className={cn(
                'rounded-xl px-4 py-3.5 transition-colors',
                isProducts
                    ? 'bg-slate-50 ring-1 ring-slate-200'
                    : 'hover:bg-slate-50/60',
            )}
        >
            <div className="flex items-start gap-3.5">
                {/* Status indicator */}
                <div className="mt-0.5 flex-shrink-0">
                    {done ? (
                        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                            <svg
                                className="h-3.5 w-3.5"
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                                strokeWidth={3}
                            >
                                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                            </svg>
                        </span>
                    ) : (
                        <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-slate-300" />
                    )}
                </div>

                {/* Content */}
                <div className="min-w-0 flex-1">
                    <p
                        className={cn(
                            'text-[15px] font-medium leading-snug',
                            done ? 'text-slate-400 line-through' : 'text-slate-900',
                        )}
                    >
                        {step.title}
                    </p>
                    <p className="mt-1 text-sm leading-relaxed text-slate-500">{step.description}</p>

                    {step.hint && !done && (
                        <p className="mt-1.5 text-[13px] leading-relaxed text-slate-400">💡 {step.hint}</p>
                    )}

                    {/* CTAs */}
                    {!done && (
                        <div className="mt-3 flex flex-wrap gap-2.5">
                            <button
                                type="button"
                                onClick={() => onNavigate?.(step.cta.href)}
                                className={cn(
                                    'rounded-lg px-4 py-2 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2',
                                    isProducts
                                        ? 'bg-brand-600 text-white hover:bg-brand-700'
                                        : 'bg-slate-900 text-white hover:bg-slate-800',
                                )}
                            >
                                {step.cta.label} →
                            </button>
                            {step.ctaSecondary && (
                                <button
                                    type="button"
                                    onClick={() => onNavigate?.(step.ctaSecondary!.href)}
                                    className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
                                >
                                    {step.ctaSecondary.label}
                                </button>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

// ─── Section group ────────────────────────────────────────────────────

interface SectionGroupProps {
    section: SetupSection;
    steps: SetupStep[];
    statusMap: StepStatusMap;
    onNavigate?: (href: string) => void;
}

function SectionGroup({ section, steps, statusMap, onNavigate }: SectionGroupProps) {
    const { completed, total } = computeProgress(steps, statusMap);
    const allDone = completed === total;

    return (
        <div>
            <div className="mb-2 flex items-center gap-2.5">
                <p className="text-xs font-bold uppercase tracking-widest text-slate-400">
                    {section.label}
                </p>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-slate-500">
                    {completed}/{total}
                </span>
            </div>

            {allDone ? (
                <p className="rounded-xl bg-emerald-50 py-3 text-center text-sm font-medium text-emerald-600">
                    ✅ Completado
                </p>
            ) : (
                <div className="space-y-1.5">
                    {steps.map((step) => (
                        <StepRow
                            key={step.id}
                            step={step}
                            status={statusMap[step.id] ?? 'pending'}
                            onNavigate={onNavigate}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}

// ─── Full setup tab ───────────────────────────────────────────────────

interface SetupTabProps {
    sections: SetupSection[];
    steps: SetupStep[];
    statusMap: StepStatusMap;
    progress: { completed: number; total: number };
    nudge: UpgradeNudge | null;
    onNavigate?: (href: string) => void;
}

export function SetupTab({
    sections,
    steps,
    statusMap,
    progress,
    nudge,
    onNavigate,
}: SetupTabProps) {
    return (
        <div className="space-y-7">
            {/* Global progress bar */}
            <div>
                <div className="mb-1.5 flex items-center justify-between">
                    <p className="text-sm font-medium text-slate-600">
                        Progreso general
                    </p>
                    <p className="text-sm font-semibold tabular-nums text-slate-900">
                        {progress.completed}/{progress.total}
                    </p>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                    <div
                        className="h-full rounded-full bg-brand-600 transition-all"
                        style={{
                            width:
                                progress.total > 0
                                    ? `${(progress.completed / progress.total) * 100}%`
                                    : '0%',
                        }}
                    />
                </div>
            </div>

            {/* Sections with their steps */}
            {sections.map((section) => {
                const sectionSteps = steps.filter((s) => s.section === section.key);
                if (sectionSteps.length === 0) return null;

                return (
                    <SectionGroup
                        key={section.key}
                        section={section}
                        steps={sectionSteps}
                        statusMap={statusMap}
                        onNavigate={onNavigate}
                    />
                );
            })}

            {/* Upgrade nudge */}
            {nudge && <UpgradeNudgeBlock nudge={nudge} onNavigate={onNavigate} />}
        </div>
    );
}
