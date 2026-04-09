'use client';

import { useCallback, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useRouter } from 'next/navigation';

import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';

import type { GestionPlan, HelpTabId, StepStatusMap } from '../types';
import { useGestionHelp } from '../use-gestion-help';
import { SetupTab } from './setup-tab';
import { HowToTab } from './howto-tab';
import { TipsTab } from './tips-tab';

interface HelpModalProps {
    open: boolean;
    onClose: () => void;
    /** Already-normalised plan. Pass `null` while still loading. */
    plan: GestionPlan | null;
    /** Initial tab to show. Defaults to 'setup'. */
    initialTab?: HelpTabId;
    /**
     * Step completion status map.
     * TODO: replace mock with data from GET /api/v1/help/setup-status/
     */
    statusMap?: StepStatusMap;
}

export function HelpModal({
    open,
    onClose,
    plan,
    initialTab = 'setup',
    statusMap = {},
}: HelpModalProps) {
    const router = useRouter();
    const { steps, sections, howto, tips, nudge, progress, resolved } = useGestionHelp(plan, statusMap);

    const handleNavigate = useCallback(
        (href: string) => {
            onClose();
            router.push(href);
        },
        [onClose, router],
    );

    // Close on Escape key
    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [open, onClose]);

    if (!open || typeof document === 'undefined') return null;

    const modal = (
        <div className="fixed inset-0 z-50" role="dialog" aria-modal="true">
            {/* Backdrop */}
            <button
                type="button"
                aria-label="Cerrar"
                onClick={onClose}
                className="absolute inset-0 h-full w-full bg-slate-900/50 backdrop-blur-[2px]"
            />

            {/* Panel */}
            <div
                className="relative z-10 flex min-h-full items-center justify-center p-4 sm:p-6"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-slate-200/60 bg-white shadow-2xl">
                    {/* Header */}
                    <div className="flex items-start justify-between border-b border-slate-100 px-6 py-5 sm:px-8">
                        <div>
                            <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
                                Gestión Comercial
                            </p>
                            <h2 className="mt-0.5 text-xl font-bold text-slate-900">
                                Centro de ayuda
                            </h2>
                        </div>
                        <button
                            type="button"
                            onClick={onClose}
                            className="-mr-1 rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                            aria-label="Cerrar"
                        >
                            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>

                    {/* Tabs + content */}
                    {!resolved ? (
                        <div className="flex items-center justify-center py-16">
                            <div className="h-7 w-7 animate-spin rounded-full border-2 border-slate-200 border-t-brand-600" />
                        </div>
                    ) : (
                    <Tabs defaultValue={initialTab} className="flex flex-1 flex-col">
                        <div className="border-b border-slate-100 px-6 pb-0 pt-4 sm:px-8">
                            <TabsList className="w-full">
                                <TabsTrigger value="setup" className="flex-1">
                                    Configuración
                                </TabsTrigger>
                                <TabsTrigger value="howto" className="flex-1">
                                    Cómo usar
                                </TabsTrigger>
                                <TabsTrigger value="tips" className="flex-1">
                                    Consejos
                                </TabsTrigger>
                            </TabsList>
                        </div>

                        <div className="max-h-[70vh] overflow-y-auto scroll-smooth px-6 py-5 sm:px-8">
                            <TabsContent value="setup">
                                <SetupTab
                                    sections={sections}
                                    steps={steps}
                                    statusMap={statusMap}
                                    progress={progress}
                                    nudge={nudge}
                                    onNavigate={handleNavigate}
                                />
                            </TabsContent>

                            <TabsContent value="howto">
                                <HowToTab
                                    items={howto}
                                    nudge={nudge}
                                    onNavigate={handleNavigate}
                                />
                            </TabsContent>

                            <TabsContent value="tips">
                                <TipsTab
                                    items={tips}
                                    nudge={nudge}
                                    onNavigate={handleNavigate}
                                />
                            </TabsContent>
                        </div>
                    </Tabs>
                    )}
                </div>
            </div>
        </div>
    );

    return createPortal(modal, document.body);
}
