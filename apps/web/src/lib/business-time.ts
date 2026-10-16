/**
 * @module business-time
 * Fechas y horas en la zona horaria IANA del Business (Slice 7D.1).
 *
 * La agenda de Turnos se muestra SIEMPRE en `Business.timezone` (la misma
 * fuente que usa el backend para `?date=` / `date_from` / `date_to`), nunca
 * en la zona del navegador ni en UTC: un admin viajando ve la misma agenda.
 *
 * - Timestamps (ISO con offset) → día/hora vía `Intl` con `timeZone`.
 * - Fechas "YYYY-MM-DD" → aritmética de calendario pura (UTC interno), sin
 *   depender de la zona del navegador ni de sus cambios de horario.
 */

/**
 * Fallback explícito si la sesión no trae timezone (sesión vieja) o trae una
 * inválida: el mismo default del proyecto que usa el backend
 * (`settings.TIME_ZONE`; `Business.timezone` también defaultea a esta zona).
 * Nunca UTC ni la zona del navegador.
 */
export const DEFAULT_BUSINESS_TIME_ZONE = 'America/Argentina/Buenos_Aires';

/** Devuelve `timeZone` si es una zona IANA válida; si no, el default del proyecto. */
export function resolveBusinessTimeZone(timeZone: string | null | undefined): string {
    if (timeZone) {
        try {
            new Intl.DateTimeFormat('en-US', { timeZone }).format(0);
            return timeZone;
        } catch {
            // zona inválida → fallback explícito
        }
    }
    return DEFAULT_BUSINESS_TIME_ZONE;
}

function parts(instant: Date, timeZone: string): Record<string, string> {
    const formatted = new Intl.DateTimeFormat('en-US', {
        timeZone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23',
    }).formatToParts(instant);
    return Object.fromEntries(formatted.map((p) => [p.type, p.value]));
}

function toDate(value: string | Date): Date {
    return value instanceof Date ? value : new Date(value);
}

/** Día local "YYYY-MM-DD" de un timestamp en `timeZone`. */
export function dateInTimeZone(value: string | Date, timeZone: string): string {
    const p = parts(toDate(value), timeZone);
    return `${p.year}-${p.month}-${p.day}`;
}

/** Hora local "HH:mm" de un timestamp en `timeZone`. */
export function timeInTimeZone(value: string | Date, timeZone: string): string {
    const p = parts(toDate(value), timeZone);
    return `${p.hour}:${p.minute}`;
}

/** "DD/MM/YYYY HH:mm" de un timestamp en `timeZone`. */
export function dateTimeInTimeZone(value: string | Date, timeZone: string): string {
    const p = parts(toDate(value), timeZone);
    return `${p.day}/${p.month}/${p.year} ${p.hour}:${p.minute}`;
}

/** Hoy "YYYY-MM-DD" en `timeZone`. */
export function todayInTimeZone(timeZone: string, now: Date = new Date()): string {
    return dateInTimeZone(now, timeZone);
}

// ── Calendario puro sobre "YYYY-MM-DD" (independiente de cualquier zona) ──

function calendarDate(yyyymmdd: string): Date {
    const [y, m, d] = yyyymmdd.split('-').map(Number);
    return new Date(Date.UTC(y, m - 1, d));
}

function calendarString(date: Date): string {
    return date.toISOString().slice(0, 10);
}

/** Suma `days` días de calendario a "YYYY-MM-DD". */
export function addCalendarDays(yyyymmdd: string, days: number): string {
    const date = calendarDate(yyyymmdd);
    date.setUTCDate(date.getUTCDate() + days);
    return calendarString(date);
}

/** Día de la semana de "YYYY-MM-DD": 0 = lunes … 6 = domingo. */
export function isoWeekdayIndex(yyyymmdd: string): number {
    return (calendarDate(yyyymmdd).getUTCDay() + 6) % 7;
}

/** { day, monthIndex (0-11), year } de "YYYY-MM-DD" sin pasar por ninguna zona. */
export function calendarParts(yyyymmdd: string): { year: number; monthIndex: number; day: number } {
    const [year, month, day] = yyyymmdd.split('-').map(Number);
    return { year, monthIndex: month - 1, day };
}
