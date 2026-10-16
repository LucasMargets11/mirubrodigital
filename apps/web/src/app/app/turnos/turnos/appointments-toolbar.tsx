import { ChevronLeft, ChevronRight, Plus } from 'lucide-react';

import { DatePicker } from '@/components/ui/date-picker';

import {
    APPOINTMENT_STATUS_LABELS,
    type AppointmentProfessional,
    type AppointmentStatus,
} from '@/features/appointments/types';
import { formatWeekLabel, weekRange, type AppointmentsView } from '@/features/appointments/week';
import { calendarParts } from '@/lib/business-time';

type AppointmentsToolbarProps = {
    view: AppointmentsView;
    onViewChange: (view: AppointmentsView) => void;
    date: string;
    onDateChange: (date: string) => void;
    /** "Hoy" del Business ("YYYY-MM-DD"), para el calendario. */
    today: string;
    onPrevious: () => void;
    onNext: () => void;
    onToday: () => void;
    /** "viernes, 2 de octubre" o "28 sep – 4 oct". */
    periodLabel: string;
    /** El período mostrado contiene el "hoy" del Business. */
    isCurrentPeriod: boolean;
    /** "3 turnos"; vacío mientras carga. */
    countLabel?: string;
    professionals: AppointmentProfessional[];
    professionalFilter: string;
    onProfessionalFilterChange: (value: string) => void;
    statusFilter: AppointmentStatus | '';
    onStatusFilterChange: (value: AppointmentStatus | '') => void;
    /** Sin handler (rol sin permiso) no se muestra "Nuevo turno". */
    onCreate?: () => void;
};

const NAV_BUTTON =
    'inline-flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 hover:border-slate-900 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-1';

const FILTER_FIELD =
    'mt-1 block w-full rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 focus:border-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900/20';

const MONTH_SHORT = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

/** "2 oct 2026". */
function formatShortDate(value: string): string {
    const { year, monthIndex, day } = calendarParts(value);
    return `${day} ${MONTH_SHORT[monthIndex]} ${year}`;
}

/**
 * Cabecera de la agenda: vista + "Nuevo turno" arriba, navegación temporal
 * con el período visible, y debajo los filtros (con menos peso visual).
 */
export function AppointmentsToolbar({
    view,
    onViewChange,
    date,
    onDateChange,
    today,
    onPrevious,
    onNext,
    onToday,
    periodLabel,
    isCurrentPeriod,
    countLabel,
    professionals,
    professionalFilter,
    onProfessionalFilterChange,
    statusFilter,
    onStatusFilterChange,
    onCreate,
}: AppointmentsToolbarProps) {
    const unit = view === 'week' ? 'Semana' : 'Día';
    // En Semana el calendario resalta la semana visible (misma regla que la agenda).
    const visibleWeek = view === 'week' ? weekRange(date) : undefined;

    return (
        <div className="space-y-4 border-b border-slate-100 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-wrap items-center gap-2">
                    <div role="group" aria-label="Vista" className="inline-flex rounded-full border border-slate-200 bg-slate-50 p-0.5 text-sm">
                        {(
                            [
                                ['day', 'Día'],
                                ['week', 'Semana'],
                            ] as const
                        ).map(([value, label]) => (
                            <button
                                key={value}
                                type="button"
                                aria-pressed={view === value}
                                onClick={() => onViewChange(value)}
                                className={`rounded-full px-4 py-1.5 font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-1 ${
                                    view === value ? 'bg-slate-900 text-white shadow-sm' : 'text-slate-600 hover:text-slate-900'
                                }`}
                            >
                                {label}
                            </button>
                        ))}
                    </div>

                    <div className="flex items-center gap-1.5">
                        <button type="button" onClick={onPrevious} aria-label={`${unit} anterior`} title={`${unit} anterior`} className={NAV_BUTTON}>
                            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                        </button>
                        <button type="button" onClick={onNext} aria-label={`${unit} siguiente`} title={`${unit} siguiente`} className={NAV_BUTTON}>
                            <ChevronRight className="h-4 w-4" aria-hidden="true" />
                        </button>
                        <button
                            type="button"
                            onClick={onToday}
                            className={`h-9 rounded-full border px-4 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-1 ${
                                isCurrentPeriod
                                    ? 'border-slate-200 bg-slate-50 text-slate-500'
                                    : 'border-slate-200 bg-white text-slate-700 hover:border-slate-900 hover:text-slate-900'
                            }`}
                        >
                            Hoy
                        </button>
                    </div>
                </div>

                {onCreate ? (
                    <button
                        type="button"
                        onClick={onCreate}
                        className="inline-flex items-center justify-center gap-1.5 rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
                    >
                        <Plus className="h-4 w-4" aria-hidden="true" />
                        Nuevo turno
                    </button>
                ) : null}
            </div>

            <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div className="min-w-0">
                    <h2 className="flex flex-wrap items-center gap-2 text-xl font-semibold text-slate-900">
                        <span className={view === 'day' ? 'capitalize' : undefined} data-testid={view === 'week' ? 'week-label' : 'day-label'}>
                            {periodLabel}
                        </span>
                        {isCurrentPeriod ? (
                            <span className="rounded-full bg-slate-900 px-2 py-0.5 text-xs font-semibold text-white">
                                {view === 'week' ? 'Esta semana' : 'Hoy'}
                            </span>
                        ) : null}
                    </h2>
                    {countLabel ? <p className="text-sm text-slate-500">{countLabel}</p> : null}
                </div>

                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:flex lg:items-end">
                    <div className="col-span-2 text-xs font-medium text-slate-500 sm:col-span-1 lg:w-48">
                        <span aria-hidden="true">Ir a fecha</span>
                        <DatePicker
                            label="Ir a fecha"
                            value={date}
                            onChange={onDateChange}
                            today={today}
                            highlightRange={visibleWeek}
                            formatValue={(value) => (visibleWeek ? formatWeekLabel(weekRange(value)) : formatShortDate(value))}
                            triggerClassName="mt-1 h-[34px] font-normal"
                        />
                    </div>
                    <label className="min-w-0 text-xs font-medium text-slate-500 lg:w-44">
                        Profesional
                        <select value={professionalFilter} onChange={(event) => onProfessionalFilterChange(event.target.value)} className={FILTER_FIELD}>
                            <option value="">Todos</option>
                            <option value="null">Sin profesional</option>
                            {professionals.map((professional) => (
                                <option key={professional.id} value={professional.id}>
                                    {professional.name}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className="min-w-0 text-xs font-medium text-slate-500 lg:w-44">
                        Estado
                        <select
                            value={statusFilter}
                            onChange={(event) => onStatusFilterChange(event.target.value as AppointmentStatus | '')}
                            className={FILTER_FIELD}
                        >
                            <option value="">Todos</option>
                            {Object.entries(APPOINTMENT_STATUS_LABELS).map(([value, label]) => (
                                <option key={value} value={value}>
                                    {label}
                                </option>
                            ))}
                        </select>
                    </label>
                </div>
            </div>
        </div>
    );
}
