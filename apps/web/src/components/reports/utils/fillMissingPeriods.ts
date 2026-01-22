export type GroupBy = 'day' | 'week' | 'month';

export type TrendPoint = {
  period: string;
  gross_sales: string;
  sales_count: number;
  avg_ticket: string;
};

export type FillMissingPeriodsParams = {
  from?: string;
  to?: string;
  groupBy?: GroupBy;
  series?: TrendPoint[];
};

const ZERO_POINT: Omit<TrendPoint, 'period'> = {
  gross_sales: '0.00',
  sales_count: 0,
  avg_ticket: '0.00',
};

export function fillMissingPeriods(params: FillMissingPeriodsParams): TrendPoint[] {
  const { from, to, groupBy = 'day', series = [] } = params;
  if (!from || !to) {
    return series;
  }

  const start = startOfInterval(new Date(from), groupBy);
  const end = startOfInterval(new Date(to), groupBy);

  const map = new Map<string, TrendPoint>();
  series.forEach((item) => {
    const key = normalizePeriod(item.period, groupBy);
    map.set(key, { ...item, period: key });
  });

  const completed: TrendPoint[] = [];
  for (let cursor = new Date(start); cursor.getTime() <= end.getTime(); cursor = addInterval(cursor, groupBy)) {
    const key = toIsoDate(cursor);
    const existing = map.get(key);
    if (existing) {
      completed.push(existing);
    } else {
      completed.push({ period: key, ...ZERO_POINT });
    }
  }

  return completed;
}

function startOfInterval(date: Date, groupBy: GroupBy): Date {
  const normalized = new Date(date);
  normalized.setHours(0, 0, 0, 0);
  if (groupBy === 'week') {
    const day = normalized.getDay();
    const diff = (day + 6) % 7; // Monday as first day
    normalized.setDate(normalized.getDate() - diff);
    return normalized;
  }
  if (groupBy === 'month') {
    normalized.setDate(1);
    return normalized;
  }
  return normalized;
}

function addInterval(date: Date, groupBy: GroupBy): Date {
  const next = new Date(date);
  if (groupBy === 'week') {
    next.setDate(next.getDate() + 7);
    return next;
  }
  if (groupBy === 'month') {
    next.setMonth(next.getMonth() + 1);
    return next;
  }
  next.setDate(next.getDate() + 1);
  return next;
}

function normalizePeriod(period: string, groupBy: GroupBy): string {
  const date = startOfInterval(new Date(period), groupBy);
  return toIsoDate(date);
}

function toIsoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}
