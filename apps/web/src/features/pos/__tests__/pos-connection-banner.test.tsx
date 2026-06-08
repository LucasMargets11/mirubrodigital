/**
 * Tests for PosConnectionBanner (PR-OFF-01).
 *
 * Coverage:
 * - Hidden while stably online.
 * - Shows the offline message (contingency not available yet) when offline.
 * - Reacts to a reconnection event.
 */

import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PosConnectionBanner } from '../components/PosConnectionBanner';
import { EmployeeSessionProvider } from '../context';

function setOnLine(value: boolean) {
  Object.defineProperty(navigator, 'onLine', {
    configurable: true,
    get: () => value,
  });
}

/**
 * The banner reads the offline catalog (PR-OFF-04), which depends on the
 * employee session + a query client. With no stored token the snapshot query
 * stays disabled, so contingency mode resolves to "no disponible".
 */
function renderBanner() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <EmployeeSessionProvider>
        <PosConnectionBanner />
      </EmployeeSessionProvider>
    </QueryClientProvider>,
  );
}

describe('PosConnectionBanner', () => {
  beforeEach(() => {
    setOnLine(true);
  });

  afterEach(() => {
    setOnLine(true);
  });

  it('renders nothing while stably online', () => {
    setOnLine(true);
    const { container } = renderBanner();
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the offline contingency message when offline', () => {
    setOnLine(false);
    renderBanner();

    const banner = screen.getByTestId('pos-connection-banner');
    expect(banner).toHaveAttribute('data-status', 'offline');
    expect(banner).toHaveTextContent(/Sin conexión — modo contingencia/i);
  });

  it('shows a reconnecting state when connection returns', () => {
    setOnLine(false);
    renderBanner();
    expect(screen.getByTestId('pos-connection-banner')).toHaveAttribute(
      'data-status',
      'offline',
    );

    act(() => {
      setOnLine(true);
      window.dispatchEvent(new Event('online'));
    });

    expect(screen.getByTestId('pos-connection-banner')).toHaveAttribute(
      'data-status',
      'reconnecting',
    );
  });
});
