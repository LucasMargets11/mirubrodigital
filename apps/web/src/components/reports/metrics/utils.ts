export type MetricTone = 'positive' | 'negative' | 'neutral';

const deltaFormatter = new Intl.NumberFormat('es-AR', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export function calculateDeltaPct(current?: number | null, previous?: number | null): number | null {
  if (current === null || current === undefined) {
    return null;
  }
  if (previous === null || previous === undefined) {
    return null;
  }
  if (previous === 0) {
    return null;
  }
  const delta = ((current - previous) / Math.abs(previous)) * 100;
  if (!Number.isFinite(delta)) {
    return null;
  }
  return delta;
}

export function getToneFromDelta(delta?: number | null): MetricTone {
  if (delta === null || delta === undefined) {
    return 'neutral';
  }
  if (delta > 3) {
    return 'positive';
  }
  if (delta < -3) {
    return 'negative';
  }
  return 'neutral';
}

export function formatDeltaLabel(delta?: number | null): string {
  if (delta === null || delta === undefined) {
    return '—';
  }
  const formatted = deltaFormatter.format(Math.abs(delta));
  if (delta > 0) {
    return `+${formatted}%`;
  }
  if (delta < 0) {
    return `-${formatted}%`;
  }
  return `${formatted}%`;
}
