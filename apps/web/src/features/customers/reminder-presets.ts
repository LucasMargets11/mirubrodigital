import { addCalendarDays, dateInTimeZone, timeInTimeZone, todayInTimeZone } from '@/lib/business-time';

/**
 * Accesos rápidos del formulario de recordatorios (CUSTOMER 07A). Solo
 * completan fecha + hora (siempre editables después); todo se calcula en la
 * zona del Business, nunca en la del navegador.
 */
export type ReminderPreset = { key: string; label: string; date: string; time: string };

/** Hora por defecto de los presets "de día" (mañana, en 3 días, próxima semana). */
export const REMINDER_DEFAULT_TIME = '09:00';

export function reminderPresets(timeZone: string, now: Date = new Date()): ReminderPreset[] {
    const inOneHour = new Date(now.getTime() + 60 * 60 * 1000);
    const today = todayInTimeZone(timeZone, now);
    return [
        { key: 'hour', label: 'En 1 hora', date: dateInTimeZone(inOneHour, timeZone), time: timeInTimeZone(inOneHour, timeZone) },
        { key: 'tomorrow', label: 'Mañana', date: addCalendarDays(today, 1), time: REMINDER_DEFAULT_TIME },
        { key: 'three-days', label: 'En 3 días', date: addCalendarDays(today, 3), time: REMINDER_DEFAULT_TIME },
        { key: 'next-week', label: 'Próxima semana', date: addCalendarDays(today, 7), time: REMINDER_DEFAULT_TIME },
    ];
}

/** "YYYY-MM-DD" + "HH:mm" → `remind_at` sin offset: el backend lo interpreta en `Business.timezone`. */
export function toRemindAt(date: string, time: string): string {
    return `${date}T${time}`;
}
