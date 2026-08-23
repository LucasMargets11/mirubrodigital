import { describe, it, expect } from 'vitest';

import {
  addCalendarMonths,
  addCalendarYears,
  isDateOnly,
  todayDateOnly,
} from '@/lib/admin/complimentary-period';

describe('complimentary-period date helpers', () => {
  it('isDateOnly accepts plain YYYY-MM-DD and rejects everything else', () => {
    expect(isDateOnly('2026-08-14')).toBe(true);
    expect(isDateOnly('2026-08-14T00:00:00Z')).toBe(false);
    expect(isDateOnly('')).toBe(false);
    expect(isDateOnly('not-a-date')).toBe(false);
  });

  it('todayDateOnly returns a YYYY-MM-DD string', () => {
    expect(isDateOnly(todayDateOnly())).toBe(true);
  });

  it('adds 6 calendar months (mid-month, no edge case)', () => {
    expect(addCalendarMonths('2026-01-15', 6)).toBe('2026-07-15');
  });

  it('adds 12 calendar months (1 year quick-pick)', () => {
    expect(addCalendarMonths('2026-01-15', 12)).toBe('2027-01-15');
  });

  it('rolls over to the next year when adding months past December', () => {
    expect(addCalendarMonths('2026-08-14', 6)).toBe('2027-02-14');
  });

  it('clamps to the last day of a shorter month (month-end edge case)', () => {
    // Jan 31 + 1 month -> Feb has only 28/29 days.
    expect(addCalendarMonths('2026-01-31', 1)).toBe('2026-02-28');
  });

  it('resolves a leap-year Feb 29 start correctly one year later', () => {
    // 2024 is a leap year; 2025 is not -> clamps to Feb 28.
    expect(addCalendarMonths('2024-02-29', 12)).toBe('2025-02-28');
  });

  it('keeps Feb 29 when the target year is also a leap year', () => {
    expect(addCalendarMonths('2024-02-29', 48)).toBe('2028-02-29');
  });

  it('addCalendarYears is equivalent to addCalendarMonths(*, years * 12)', () => {
    expect(addCalendarYears('2026-03-10', 1)).toBe(addCalendarMonths('2026-03-10', 12));
  });

  it('returns the input unchanged for a non date-only string', () => {
    expect(addCalendarMonths('not-a-date', 6)).toBe('not-a-date');
  });
});
