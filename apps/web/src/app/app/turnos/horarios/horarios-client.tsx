"use client";

import { useMemo, useState } from 'react';

import { useAppointmentProfessionals } from '@/features/appointments/hooks';
import { cn } from '@/lib/utils';

import { ExceptionsPanel } from './exceptions-panel';
import { ScheduleWeekEditor } from './schedule-week-editor';

type TabKey = 'general' | 'profesional' | 'excepciones';

const TABS: { key: TabKey; label: string }[] = [
    { key: 'general', label: 'Horario general' },
    { key: 'profesional', label: 'Por profesional' },
    { key: 'excepciones', label: 'Excepciones' },
];

type HorariosClientProps = {
    canManage: boolean;
};

export function HorariosClient({ canManage }: HorariosClientProps) {
    const [tab, setTab] = useState<TabKey>('general');
    const [selectedProfessionalId, setSelectedProfessionalId] = useState<string>('');
    const [exceptionScope, setExceptionScope] = useState<string>('');

    const professionalsQuery = useAppointmentProfessionals();
    const professionals = useMemo(() => professionalsQuery.data ?? [], [professionalsQuery.data]);

    return (
        <div className="space-y-4">
            <nav aria-label="Secciones de Horarios" className="border-b border-slate-200">
                <div className="flex gap-0 -mb-px overflow-x-auto">
                    {TABS.map(({ key, label }) => (
                        <button
                            key={key}
                            type="button"
                            onClick={() => setTab(key)}
                            className={cn(
                                'whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 rounded-t-sm',
                                tab === key
                                    ? 'border-slate-900 text-slate-900'
                                    : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                            )}
                            aria-current={tab === key ? 'page' : undefined}
                        >
                            {label}
                        </button>
                    ))}
                </div>
            </nav>

            {tab === 'general' && (
                <div className="space-y-3">
                    <p className="text-sm text-slate-500">
                        Este es el horario base del negocio. Se aplica a los profesionales que no tengan un horario propio configurado.
                    </p>
                    <ScheduleWeekEditor professionalId={null} canManage={canManage} />
                </div>
            )}

            {tab === 'profesional' && (
                <div className="space-y-3">
                    {professionals.length === 0 ? (
                        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
                            Todavía no cargaste profesionales. Creá uno en la sección Profesionales para poder asignarle un horario propio.
                        </div>
                    ) : (
                        <>
                            <label className="block max-w-sm text-sm font-medium text-slate-700">
                                Profesional
                                <select
                                    value={selectedProfessionalId}
                                    onChange={(event) => setSelectedProfessionalId(event.target.value)}
                                    className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                >
                                    <option value="">Seleccioná un profesional</option>
                                    {professionals.map((professional) => (
                                        <option key={professional.id} value={professional.id}>{professional.name}</option>
                                    ))}
                                </select>
                            </label>

                            {selectedProfessionalId ? (
                                <ScheduleWeekEditor professionalId={selectedProfessionalId} canManage={canManage} />
                            ) : (
                                <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
                                    Elegí un profesional para ver y editar su horario.
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}

            {tab === 'excepciones' && (
                <div className="space-y-3">
                    <label className="block max-w-sm text-sm font-medium text-slate-700">
                        Alcance
                        <select
                            value={exceptionScope}
                            onChange={(event) => setExceptionScope(event.target.value)}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        >
                            <option value="">Negocio (horario general)</option>
                            {professionals.map((professional) => (
                                <option key={professional.id} value={professional.id}>{professional.name}</option>
                            ))}
                        </select>
                    </label>
                    <ExceptionsPanel professionalId={exceptionScope || null} canManage={canManage} />
                </div>
            )}
        </div>
    );
}
