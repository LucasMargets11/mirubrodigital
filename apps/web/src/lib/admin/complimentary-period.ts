/**
 * ADMIN-CLIENTES 03C — calendar-month/year arithmetic for the "Nuevo cliente"
 * complimentary period quick-picks (6 meses / 1 año).
 *
 * Pure string/integer math — never routes a value through the JS Date
 * constructor's local-vs-UTC parsing ambiguity, so the selected calendar
 * day never shifts. Date.UTC() is only used to look up how many days a
 * given month has (a pure calendar fact, not a timezone-sensitive instant).
 */

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

/** True for a bare "YYYY-MM-DD" string (what <input type="date"> produces). */
export function isDateOnly(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

/** Today's calendar date (local), as "YYYY-MM-DD". */
export function todayDateOnly(): string {
  const now = new Date();
  return `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`;
}

/**
 * Add `months` calendar months to a "YYYY-MM-DD" date, clamping the day to
 * the last day of the resulting month (handles month-end and leap years,
 * e.g. 2024-02-29 + 12 months -> 2025-02-28). Returns the input unchanged
 * if it isn't a valid "YYYY-MM-DD" string.
 */
export function addCalendarMonths(dateOnly: string, months: number): string {
  if (!isDateOnly(dateOnly)) return dateOnly;

  const [year, month, day] = dateOnly.split('-').map(Number);
  const totalMonths = year * 12 + (month - 1) + months;
  const newYear = Math.floor(totalMonths / 12);
  const newMonthIndex = ((totalMonths % 12) + 12) % 12; // 0-based, negative-safe

  const daysInNewMonth = new Date(Date.UTC(newYear, newMonthIndex + 1, 0)).getUTCDate();
  const newDay = Math.min(day, daysInNewMonth);

  return `${newYear}-${pad2(newMonthIndex + 1)}-${pad2(newDay)}`;
}

/** Add `years` calendar years — implemented as `years * 12` calendar months. */
export function addCalendarYears(dateOnly: string, years: number): string {
  return addCalendarMonths(dateOnly, years * 12);
}
