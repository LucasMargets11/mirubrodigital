"use client";

import {
    useCallback,
    useEffect,
    useId,
    useLayoutEffect,
    useMemo,
    useRef,
    useState,
    useSyncExternalStore,
    type KeyboardEvent as ReactKeyboardEvent,
    type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { CalendarDays, ChevronLeft, ChevronRight, X } from 'lucide-react';

import { addCalendarDays, calendarParts, isoWeekdayIndex } from '@/lib/business-time';
import { cn } from '@/lib/utils';

/*
 * Selector de fecha propio (Slice UI 02): reemplaza al `<input type="date">`.
 *
 * Trabaja SOLO con fechas de calendario "YYYY-MM-DD" y la aritmética pura de
 * `business-time` (sin `new Date("YYYY-MM-DD")` ni zona del navegador). El
 * "hoy" lo decide quien lo usa (p.ej. `todayInTimeZone(Business.timezone)`)
 * y llega por la prop `today`.
 *
 * Desktop: popover anclado al trigger (abre hacia arriba si no entra abajo).
 * Mobile (<640px): bottom sheet modal con celdas táctiles de 44px.
 */

const WEEKDAY_MIN = ['LU', 'MA', 'MI', 'JU', 'VI', 'SA', 'DO'];
const WEEKDAY_LONG = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
const MONTH_LONG = [
    'enero',
    'febrero',
    'marzo',
    'abril',
    'mayo',
    'junio',
    'julio',
    'agosto',
    'septiembre',
    'octubre',
    'noviembre',
    'diciembre',
];

const NAV_BUTTON =
    'inline-flex items-center justify-center rounded-full text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent';

const MOBILE_QUERY = '(max-width: 639px)';
const VIEWPORT_MARGIN = 8;
const TRIGGER_GAP = 6;

type MonthRef = { year: number; monthIndex: number };

function pad(value: number): string {
    return String(value).padStart(2, '0');
}

function monthStart({ year, monthIndex }: MonthRef): string {
    return `${year}-${pad(monthIndex + 1)}-01`;
}

function shiftMonth({ year, monthIndex }: MonthRef, delta: number): MonthRef {
    const total = year * 12 + monthIndex + delta;
    return { year: Math.floor(total / 12), monthIndex: ((total % 12) + 12) % 12 };
}

function monthOf(date: string): MonthRef {
    const { year, monthIndex } = calendarParts(date);
    return { year, monthIndex };
}

function lastDayOfMonth(month: MonthRef): string {
    return addCalendarDays(monthStart(shiftMonth(month, 1)), -1);
}

/** 42 días (6 semanas, lunes → domingo) que cubren el mes. Alto fijo: el popover no salta. */
function monthGrid(month: MonthRef): string[] {
    const first = monthStart(month);
    const gridStart = addCalendarDays(first, -isoWeekdayIndex(first));
    return Array.from({ length: 42 }, (_, i) => addCalendarDays(gridStart, i));
}

/** "viernes, 2 de octubre de 2026" sin pasar por ninguna zona horaria. */
export function formatLongDate(date: string): string {
    const { year, monthIndex, day } = calendarParts(date);
    return `${WEEKDAY_LONG[isoWeekdayIndex(date)]}, ${day} de ${MONTH_LONG[monthIndex]} de ${year}`;
}

/** "2 de octubre de 2026". */
export function formatMediumDate(date: string): string {
    const { year, monthIndex, day } = calendarParts(date);
    return `${day} de ${MONTH_LONG[monthIndex]} de ${year}`;
}

function formatMonthTitle({ year, monthIndex }: MonthRef): string {
    const name = MONTH_LONG[monthIndex];
    return `${name.charAt(0).toUpperCase()}${name.slice(1)} ${year}`;
}

/* ── Calendario mensual (inline) ─────────────────────────────────────── */

export type CalendarProps = {
    /** Fecha seleccionada "YYYY-MM-DD" (o vacío). */
    value: string;
    onSelect: (date: string) => void;
    /** "Hoy" en la zona que corresponda (Business), "YYYY-MM-DD". */
    today: string;
    /** Fechas anteriores a `min` quedan deshabilitadas. */
    min?: string;
    max?: string;
    isDateDisabled?: (date: string) => boolean;
    /** Rango resaltado (p.ej. la semana visible en la vista Semana). */
    highlightRange?: { from: string; to: string };
    /** Celdas más grandes para touch (sheet mobile). */
    size?: 'default' | 'touch';
    tone?: 'neutral' | 'brand';
    /** Enfoca el día activo al montar (al abrir el popover/sheet). */
    autoFocus?: boolean;
};

export function Calendar({
    value,
    onSelect,
    today,
    min,
    max,
    isDateDisabled,
    highlightRange,
    size = 'default',
    tone = 'neutral',
    autoFocus = false,
}: CalendarProps) {
    const titleId = useId();
    const isDisabled = useCallback(
        (date: string) => (min !== undefined && date < min) || (max !== undefined && date > max) || Boolean(isDateDisabled?.(date)),
        [min, max, isDateDisabled],
    );

    const [focusedDate, setFocusedDate] = useState(() => value || today);
    const [month, setMonth] = useState<MonthRef>(() => monthOf(value || today));
    const gridRef = useRef<HTMLDivElement>(null);
    const shouldFocusRef = useRef(autoFocus);

    const days = useMemo(() => monthGrid(month), [month]);
    const canGoPrev = min === undefined || lastDayOfMonth(shiftMonth(month, -1)) >= min;
    const canGoNext = max === undefined || monthStart(shiftMonth(month, 1)) <= max;

    useEffect(() => {
        if (!shouldFocusRef.current) return;
        shouldFocusRef.current = false;
        gridRef.current?.querySelector<HTMLButtonElement>(`[data-date="${focusedDate}"]`)?.focus();
    }, [focusedDate, month]);

    function moveFocus(date: string) {
        if (min !== undefined && date < min) date = min;
        if (max !== undefined && date > max) date = max;
        setFocusedDate(date);
        const target = monthOf(date);
        if (target.year !== month.year || target.monthIndex !== month.monthIndex) setMonth(target);
        shouldFocusRef.current = true;
    }

    function goToMonth(delta: number) {
        const next = shiftMonth(month, delta);
        setMonth(next);
        // El foco de teclado (roving tabindex) acompaña al mes visible.
        const { day } = calendarParts(focusedDate);
        const last = calendarParts(lastDayOfMonth(next)).day;
        setFocusedDate(`${next.year}-${pad(next.monthIndex + 1)}-${pad(Math.min(day, last))}`);
    }

    function handleKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
        const weekday = isoWeekdayIndex(focusedDate);
        const { day } = calendarParts(focusedDate);
        const keyMoves: Record<string, () => string> = {
            ArrowLeft: () => addCalendarDays(focusedDate, -1),
            ArrowRight: () => addCalendarDays(focusedDate, 1),
            ArrowUp: () => addCalendarDays(focusedDate, -7),
            ArrowDown: () => addCalendarDays(focusedDate, 7),
            Home: () => addCalendarDays(focusedDate, -weekday),
            End: () => addCalendarDays(focusedDate, 6 - weekday),
            PageUp: () => {
                const prev = shiftMonth(monthOf(focusedDate), event.shiftKey ? -12 : -1);
                const last = calendarParts(lastDayOfMonth(prev)).day;
                return `${prev.year}-${pad(prev.monthIndex + 1)}-${pad(Math.min(day, last))}`;
            },
            PageDown: () => {
                const next = shiftMonth(monthOf(focusedDate), event.shiftKey ? 12 : 1);
                const last = calendarParts(lastDayOfMonth(next)).day;
                return `${next.year}-${pad(next.monthIndex + 1)}-${pad(Math.min(day, last))}`;
            },
        };
        const move = keyMoves[event.key];
        if (!move) return;
        event.preventDefault();
        moveFocus(move());
    }

    const todayDisabled = isDisabled(today);
    const cell = size === 'touch' ? 'h-11 w-11 text-base' : 'h-9 w-9 text-sm';
    const selectedClass =
        tone === 'brand'
            ? 'bg-brand-600 font-semibold text-white hover:bg-brand-600'
            : 'bg-slate-900 font-semibold text-white hover:bg-slate-900';
    const ringClass = tone === 'brand' ? 'focus-visible:ring-brand-500' : 'focus-visible:ring-slate-900';

    return (
        <div className="select-none">
            <div className="flex items-center justify-between gap-2 pb-2 pl-1">
                <h2 id={titleId} className="text-sm font-semibold text-slate-900" aria-live="polite">
                    {formatMonthTitle(month)}
                </h2>
                <div className="flex items-center gap-1">
                    <button
                        type="button"
                        onClick={() => onSelect(today)}
                        disabled={todayDisabled}
                        className={cn(
                            'mr-1 rounded-full border border-slate-200 px-3 text-xs font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-40',
                            ringClass,
                            size === 'touch' ? 'h-11 px-4 text-sm' : 'h-8',
                        )}
                    >
                        Hoy
                    </button>
                    <button
                        type="button"
                        onClick={() => goToMonth(-1)}
                        disabled={!canGoPrev}
                        aria-label="Mes anterior"
                        title="Mes anterior"
                        className={cn(NAV_BUTTON, ringClass, size === 'touch' ? 'h-11 w-11' : 'h-8 w-8')}
                    >
                        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                    </button>
                    <button
                        type="button"
                        onClick={() => goToMonth(1)}
                        disabled={!canGoNext}
                        aria-label="Mes siguiente"
                        title="Mes siguiente"
                        className={cn(NAV_BUTTON, ringClass, size === 'touch' ? 'h-11 w-11' : 'h-8 w-8')}
                    >
                        <ChevronRight className="h-4 w-4" aria-hidden="true" />
                    </button>
                </div>
            </div>

            <div role="grid" aria-labelledby={titleId} ref={gridRef} onKeyDown={handleKeyDown} className="mx-auto w-max">
                <div role="row" className="grid grid-cols-7">
                    {WEEKDAY_MIN.map((label, i) => (
                        <div
                            key={label}
                            role="columnheader"
                            aria-label={WEEKDAY_LONG[i]}
                            className={cn('flex items-center justify-center text-[11px] font-semibold text-slate-400', size === 'touch' ? 'h-8 w-11' : 'h-7 w-9')}
                        >
                            {label}
                        </div>
                    ))}
                </div>
                {Array.from({ length: 6 }, (_, rowIndex) => (
                    <div role="row" key={rowIndex} className="grid grid-cols-7">
                        {days.slice(rowIndex * 7, rowIndex * 7 + 7).map((date) => {
                            const { monthIndex, day } = calendarParts(date);
                            const outside = monthIndex !== month.monthIndex;
                            const selected = date === value;
                            const isToday = date === today;
                            const disabled = isDisabled(date);
                            const inRange = Boolean(highlightRange && date >= highlightRange.from && date <= highlightRange.to);
                            const labelParts = [formatLongDate(date)];
                            if (isToday) labelParts.push('hoy');
                            if (disabled) labelParts.push('no disponible');
                            return (
                                <div role="gridcell" key={date} aria-selected={selected} className="flex items-center justify-center p-px">
                                    <button
                                        type="button"
                                        data-date={date}
                                        tabIndex={date === focusedDate ? 0 : -1}
                                        disabled={disabled}
                                        aria-label={labelParts.join(', ')}
                                        aria-current={isToday ? 'date' : undefined}
                                        aria-pressed={selected}
                                        onClick={() => onSelect(date)}
                                        onFocus={() => setFocusedDate(date)}
                                        className={cn(
                                            'relative inline-flex items-center justify-center rounded-full tabular-nums transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1',
                                            ringClass,
                                            cell,
                                            outside ? 'text-slate-400' : 'text-slate-700',
                                            inRange && !selected && 'bg-slate-100 text-slate-900',
                                            !disabled && !selected && 'hover:bg-slate-100 hover:text-slate-900',
                                            isToday && !selected && 'font-semibold ring-1 ring-inset ring-slate-400',
                                            selected && selectedClass,
                                            disabled && 'cursor-not-allowed text-slate-300 line-through decoration-slate-300',
                                        )}
                                    >
                                        {day}
                                        {isToday ? (
                                            <span
                                                aria-hidden="true"
                                                className={cn(
                                                    'absolute bottom-1 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full',
                                                    selected ? 'bg-white' : 'bg-slate-500',
                                                )}
                                            />
                                        ) : null}
                                    </button>
                                </div>
                            );
                        })}
                    </div>
                ))}
            </div>
        </div>
    );
}

/* ── Selector (trigger + popover / sheet) ────────────────────────────── */

function subscribeMobile(onChange: () => void): () => void {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return () => {};
    const query = window.matchMedia(MOBILE_QUERY);
    query.addEventListener?.('change', onChange);
    return () => query.removeEventListener?.('change', onChange);
}

function readMobile(): boolean {
    return typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(MOBILE_QUERY).matches;
}

function useIsMobile(): boolean {
    return useSyncExternalStore(subscribeMobile, readMobile, () => false);
}

function focusableIn(container: HTMLElement): HTMLElement[] {
    return Array.from(container.querySelectorAll<HTMLElement>('button:not([disabled]), [tabindex="0"]')).filter(
        (el) => el.tabIndex >= 0,
    );
}

export type DatePickerProps = Omit<CalendarProps, 'onSelect' | 'size' | 'autoFocus'> & {
    onChange: (date: string) => void;
    /** Nombre accesible del campo ("Fecha", "Ir a fecha"). */
    label: string;
    id?: string;
    placeholder?: string;
    /** Texto visible del trigger; por defecto "2 de octubre de 2026". */
    formatValue?: (date: string) => ReactNode;
    triggerClassName?: string;
    /** Título del sheet mobile. */
    sheetTitle?: string;
};

export function DatePicker({
    value,
    onChange,
    label,
    id,
    placeholder = 'Elegí una fecha',
    formatValue = formatMediumDate,
    triggerClassName,
    sheetTitle = 'Elegí una fecha',
    tone = 'neutral',
    ...calendarProps
}: DatePickerProps) {
    const [open, setOpen] = useState(false);
    const mobile = useIsMobile();
    const triggerRef = useRef<HTMLButtonElement>(null);
    const panelRef = useRef<HTMLDivElement>(null);
    const dialogId = useId();
    const [position, setPosition] = useState<{ top: number; left: number; maxHeight?: number } | null>(null);

    const close = useCallback((restoreFocus = true) => {
        setOpen(false);
        setPosition(null);
        if (restoreFocus) triggerRef.current?.focus();
    }, []);

    function handleSelect(date: string) {
        onChange(date);
        close();
    }

    // Popover desktop: debajo del trigger; arriba si no entra; siempre dentro del viewport.
    const updatePosition = useCallback(() => {
        const trigger = triggerRef.current;
        const panel = panelRef.current;
        if (!trigger || !panel) return;
        const rect = trigger.getBoundingClientRect();
        const width = panel.offsetWidth;
        // Alto natural (sin el maxHeight de una medición anterior), bordes incluidos.
        const height = panel.scrollHeight + (panel.offsetHeight - panel.clientHeight);
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const spaceBelow = vh - rect.bottom - TRIGGER_GAP - VIEWPORT_MARGIN;
        const spaceAbove = rect.top - TRIGGER_GAP - VIEWPORT_MARGIN;
        let top: number;
        let maxHeight: number | undefined;
        if (height <= spaceBelow) {
            top = rect.bottom + TRIGGER_GAP;
        } else if (height <= spaceAbove) {
            top = rect.top - TRIGGER_GAP - height;
        } else if (height <= vh - 2 * VIEWPORT_MARGIN) {
            // No entra ni arriba ni abajo: entero dentro del viewport, aunque tape el trigger.
            top = Math.min(Math.max(rect.bottom + TRIGGER_GAP, VIEWPORT_MARGIN), vh - VIEWPORT_MARGIN - height);
        } else {
            top = VIEWPORT_MARGIN;
            maxHeight = vh - 2 * VIEWPORT_MARGIN;
        }
        const left = Math.min(Math.max(rect.left, VIEWPORT_MARGIN), Math.max(VIEWPORT_MARGIN, vw - width - VIEWPORT_MARGIN));
        setPosition({ top, left, maxHeight });
    }, []);

    useLayoutEffect(() => {
        if (!open || mobile) return;
        updatePosition();
        window.addEventListener('resize', updatePosition);
        window.addEventListener('scroll', updatePosition, true);
        return () => {
            window.removeEventListener('resize', updatePosition);
            window.removeEventListener('scroll', updatePosition, true);
        };
    }, [open, mobile, updatePosition]);

    // Click afuera cierra (sin devolver el foco: el usuario ya está en otro lado).
    useEffect(() => {
        if (!open) return;
        const handlePointerDown = (event: PointerEvent | MouseEvent) => {
            const target = event.target as Node;
            if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
            close(false);
        };
        document.addEventListener('mousedown', handlePointerDown);
        return () => document.removeEventListener('mousedown', handlePointerDown);
    }, [open, close]);

    // Sheet mobile: bloquea el scroll del body mientras está abierto.
    useEffect(() => {
        if (!open || !mobile) return;
        const previous = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        return () => {
            document.body.style.overflow = previous;
        };
    }, [open, mobile]);

    function handlePanelKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
        if (event.key === 'Escape') {
            // No dejar que el Escape cierre también un Modal/Drawer contenedor.
            event.preventDefault();
            event.stopPropagation();
            close();
            return;
        }
        if (event.key === 'Tab' && panelRef.current) {
            const items = focusableIn(panelRef.current);
            if (items.length === 0) return;
            const first = items[0];
            const last = items[items.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }
    }

    const display = value ? formatValue(value) : placeholder;
    const ariaLabel = `${label}: ${value ? formatLongDate(value) : 'sin fecha elegida'}`;

    const calendar = (
        <Calendar
            {...calendarProps}
            value={value}
            onSelect={handleSelect}
            tone={tone}
            size={mobile ? 'touch' : 'default'}
            autoFocus
        />
    );

    let panel: ReactNode = null;
    if (open && typeof document !== 'undefined') {
        panel = createPortal(
            mobile ? (
                <div className="fixed inset-0 z-[60] flex items-end justify-center">
                    <div className="absolute inset-0 bg-slate-900/50" aria-hidden="true" onClick={() => close()} />
                    <div
                        ref={panelRef}
                        id={dialogId}
                        role="dialog"
                        aria-modal="true"
                        aria-label={sheetTitle}
                        onKeyDown={handlePanelKeyDown}
                        className="relative w-full max-w-md rounded-t-3xl bg-white px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 shadow-2xl"
                    >
                        <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-slate-200" aria-hidden="true" />
                        <div className="mb-2 flex items-center justify-between">
                            <p className="text-sm font-semibold text-slate-900">{sheetTitle}</p>
                            <button
                                type="button"
                                onClick={() => close()}
                                aria-label="Cerrar calendario"
                                className="inline-flex h-11 w-11 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900"
                            >
                                <X className="h-5 w-5" aria-hidden="true" />
                            </button>
                        </div>
                        {calendar}
                    </div>
                </div>
            ) : (
                <div
                    ref={panelRef}
                    id={dialogId}
                    role="dialog"
                    aria-label={sheetTitle}
                    onKeyDown={handlePanelKeyDown}
                    style={{
                        top: position?.top ?? 0,
                        left: position?.left ?? 0,
                        maxHeight: position?.maxHeight,
                        visibility: position ? 'visible' : 'hidden',
                    }}
                    className="fixed z-[60] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-3 shadow-lg"
                >
                    {calendar}
                </div>
            ),
            document.body,
        );
    }

    return (
        <>
            <button
                ref={triggerRef}
                id={id}
                type="button"
                aria-label={ariaLabel}
                aria-haspopup="dialog"
                aria-expanded={open}
                aria-controls={open ? dialogId : undefined}
                data-value={value}
                onClick={() => (open ? close(false) : setOpen(true))}
                className={cn(
                    'flex w-full items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-left text-sm text-slate-700 hover:border-slate-400 focus-visible:outline-none focus-visible:ring-2',
                    tone === 'brand' ? 'focus-visible:ring-brand-500/40' : 'focus-visible:ring-slate-900/20',
                    open && 'border-slate-400',
                    triggerClassName,
                )}
            >
                <CalendarDays className="h-4 w-4 shrink-0 text-slate-400" aria-hidden="true" />
                <span className={cn('min-w-0 flex-1 truncate first-letter:uppercase', !value && 'text-slate-400')}>{display}</span>
            </button>
            {panel}
        </>
    );
}
