/* ── Semana del calendario interno de Turnos (Slice 7D) ──────────────────
 * Única definición de "semana" del panel: lunes → domingo, en fechas
 * "YYYY-MM-DD" del Business. El backend recibe el rango como
 * `date_from`/`date_to` y lo interpreta en `Business.timezone`; acá se
 * agrupa con esa misma zona (7D.1), nunca con la del navegador.
 */
import { addCalendarDays, calendarParts, dateInTimeZone, isoWeekdayIndex } from '@/lib/business-time';

import type { Appointment } from './types';

export type AppointmentsView = 'day' | 'week';

export type WeekRange = {
    /** Lunes de la semana. */
    from: string;
    /** Domingo de la semana. */
    to: string;
    /** Los 7 días, lunes → domingo. */
    days: string[];
};

export const WEEKDAY_SHORT = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
const MONTH_SHORT = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

/** Lunes de la semana que contiene `date`. */
export function startOfWeek(date: string): string {
    return addCalendarDays(date, -isoWeekdayIndex(date));
}

export function weekRange(date: string): WeekRange {
    const from = startOfWeek(date);
    const days = Array.from({ length: 7 }, (_, i) => addCalendarDays(from, i));
    return { from, to: days[6], days };
}

function shortDate(date: string): string {
    const { day, monthIndex } = calendarParts(date);
    return `${day} ${MONTH_SHORT[monthIndex]}`;
}

/** "29 sep – 5 oct". */
export function formatWeekLabel(range: WeekRange): string {
    return `${shortDate(range.from)} – ${shortDate(range.to)}`;
}

/** "Lun 29". */
export function formatWeekdayLabel(date: string): string {
    return `${WEEKDAY_SHORT[isoWeekdayIndex(date)]} ${calendarParts(date).day}`;
}

/** "1 turno" / "3 turnos". */
export function formatAppointmentCount(count: number): string {
    return count === 1 ? '1 turno' : `${count} turnos`;
}

/**
 * Agrupa los turnos por el día de `start_at` en la timezone del Business
 * (la misma que usa el backend para el rango) y los ordena por hora.
 * Siempre devuelve las 7 claves de la semana.
 */
export function groupAppointmentsByDay(
    appointments: Appointment[],
    days: string[],
    timeZone: string,
): Record<string, Appointment[]> {
    const groups: Record<string, Appointment[]> = Object.fromEntries(days.map((day) => [day, []]));
    for (const appointment of appointments) {
        const day = dateInTimeZone(appointment.start_at, timeZone);
        groups[day]?.push(appointment);
    }
    for (const day of days) {
        groups[day].sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime());
    }
    return groups;
}
