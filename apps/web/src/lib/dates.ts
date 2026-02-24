/**
 * @module dates
 * Capa central de manejo de fechas — America/Argentina/Buenos_Aires (UTC-3).
 *
 * REGLA DE ORO:
 *  - date-only (ej: fecha de reposición, gasto, presupuesto)
 *      → guardar como "YYYY-MM-DD"; mostrar con formatDateAR()
 *      → NUNCA usar toISOString() (convierte a UTC y puede cambiar el día)
 *  - datetime (ej: created_at, occurred_at en transacciones)
 *      → mostrar con formatDateTimeAR() o formatDateFromTimestampAR()
 *  - "Hoy" en formularios/filtros  → siempre via todayDateString()
 */

const AR_TZ = 'America/Argentina/Buenos_Aires';
const AR_LOCALE = 'es-AR';

// ─────────────────────────────────────────────────────────────────────────────
// "Hoy" y aritmética de fechas
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Devuelve "YYYY-MM-DD" representando HOY en timezone AR.
 * Funciona tanto en el browser (timezone cualquiera) como en el servidor Node UTC.
 */
export function todayDateString(): string {
  // en-CA produce "YYYY-MM-DD"; timeZone fuerza el cálculo en AR.
  return new Intl.DateTimeFormat('en-CA', { timeZone: AR_TZ }).format(new Date());
}

/**
 * "YYYY-MM-DD" + offset de días → nueva "YYYY-MM-DD".
 * El offset puede ser negativo (pasado) o positivo (futuro).
 */
export function dateOffsetFromToday(daysOffset: number): string {
  return addDaysToDateString(todayDateString(), daysOffset);
}

/**
 * Suma N días a una string "YYYY-MM-DD" y devuelve "YYYY-MM-DD".
 * Usa Date local para la aritmética (no UTC), libre de corrimientos.
 */
export function addDaysToDateString(yyyymmdd: string, days: number): string {
  const [y, m, d] = yyyymmdd.split('-').map(Number);
  const date = new Date(y, m - 1, d + days); // local midnight, no UTC shift
  return localDateToString(date);
}

/**
 * Devuelve el primer día del mes actual en AR → "YYYY-MM-01".
 */
export function startOfCurrentMonthDateString(): string {
  const today = todayDateString();
  return `${today.slice(0, 7)}-01`;
}

/**
 * Dado "YYYY-MM", devuelve "YYYY-MM-DD" del último día de ese mes.
 */
export function endOfMonthDateString(yearMonth: string): string {
  const [y, m] = yearMonth.split('-').map(Number);
  const lastDay = new Date(y, m, 0).getDate(); // day 0 del mes siguiente = último día
  return `${yearMonth}-${String(lastDay).padStart(2, '0')}`;
}

/**
 * { from, to } del mes actual en AR.
 */
export function currentMonthRange(): { from: string; to: string } {
  const today = todayDateString();
  const yearMonth = today.slice(0, 7);
  return { from: `${yearMonth}-01`, to: endOfMonthDateString(yearMonth) };
}

/**
 * { from, to } del mes anterior en AR.
 */
export function previousMonthRange(): { from: string; to: string } {
  const today = todayDateString();
  const [year, month] = today.split('-').map(Number);
  const prevMonth = month === 1 ? 12 : month - 1;
  const prevYear = month === 1 ? year - 1 : year;
  const yearMonth = `${prevYear}-${String(prevMonth).padStart(2, '0')}`;
  return { from: `${yearMonth}-01`, to: endOfMonthDateString(yearMonth) };
}

// ─────────────────────────────────────────────────────────────────────────────
// Conversión Date ↔ "YYYY-MM-DD" (sin UTC shift)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Date → "YYYY-MM-DD" usando el tiempo LOCAL del objeto (no UTC).
 * Útil para convertir objetos Date creados con `new Date(y, m, d)`.
 */
export function localDateToString(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/**
 * "YYYY-MM-DD" → Date en medianoche LOCAL.
 * Evita el bug de `new Date("YYYY-MM-DD")` que parsea como UTC midnight
 * (lo cual en AR UTC-3 se convierte al día anterior a las 21:00).
 */
export function parseDateOnly(yyyymmdd: string): Date {
  const [y, m, d] = yyyymmdd.split('-').map(Number);
  return new Date(y, m - 1, d); // local midnight, no UTC
}

// ─────────────────────────────────────────────────────────────────────────────
// Formateo para DISPLAY
// ─────────────────────────────────────────────────────────────────────────────

/**
 * "YYYY-MM-DD" → "DD/MM/YYYY"
 * Operación de string pura: sin parseo Date, sin UTC shift, siempre correcto.
 * Usar para campos date-only (fecha de reposición, gasto, presupuesto, etc.).
 */
export function formatDateAR(yyyymmdd: string | null | undefined): string {
  if (!yyyymmdd) return '—';
  const parts = yyyymmdd.split('-');
  if (parts.length !== 3) return yyyymmdd;
  return `${parts[2]}/${parts[1]}/${parts[0]}`;
}

/**
 * ISO datetime (con Z o con offset) → "DD/MM/YYYY HH:mm" en timezone AR.
 * Usar para timestamps: created_at, occurred_at de transacciones, etc.
 */
export function formatDateTimeAR(isoString: string | null | undefined): string {
  if (!isoString) return '—';
  try {
    return new Intl.DateTimeFormat(AR_LOCALE, {
      timeZone: AR_TZ,
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(new Date(isoString));
  } catch {
    return isoString;
  }
}

/**
 * ISO datetime (con Z o con offset) → "DD/MM/YYYY" en timezone AR (sin hora).
 * Usar para mostrar created_at como solo fecha en tablas.
 */
export function formatDateFromTimestampAR(isoString: string | null | undefined): string {
  if (!isoString) return '—';
  try {
    return new Intl.DateTimeFormat(AR_LOCALE, {
      timeZone: AR_TZ,
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(new Date(isoString));
  } catch {
    return isoString;
  }
}

/**
 * "YYYY-MM-DD" → "DD/MM" (para labels cortos en charts, sin año).
 * String pura, sin UTC shift.
 */
export function formatDateShortAR(yyyymmdd: string | null | undefined): string {
  if (!yyyymmdd) return '—';
  const parts = yyyymmdd.split('-');
  if (parts.length !== 3) return yyyymmdd ?? '—';
  return `${parts[2]}/${parts[1]}`;
}
