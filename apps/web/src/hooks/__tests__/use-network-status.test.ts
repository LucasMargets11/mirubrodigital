/**
 * Tests for useNetworkStatus (PR-OFF-01).
 *
 * Coverage:
 * - Reports initial online/offline state from navigator.onLine.
 * - Reacts to window 'offline' / 'online' events.
 * - Emits a transient 'reconnecting' status on reconnection.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useNetworkStatus } from '../use-network-status';

function setOnLine(value: boolean) {
  Object.defineProperty(navigator, 'onLine', {
    configurable: true,
    get: () => value,
  });
}

describe('useNetworkStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setOnLine(true);
  });

  afterEach(() => {
    vi.useRealTimers();
    setOnLine(true);
  });

  it('reports online when navigator.onLine is true', () => {
    setOnLine(true);
    const { result } = renderHook(() => useNetworkStatus());
    expect(result.current.isOnline).toBe(true);
    expect(result.current.isOffline).toBe(false);
    expect(result.current.status).toBe('online');
  });

  it('reports offline when navigator.onLine is false', () => {
    setOnLine(false);
    const { result } = renderHook(() => useNetworkStatus());
    expect(result.current.isOnline).toBe(false);
    expect(result.current.isOffline).toBe(true);
    expect(result.current.status).toBe('offline');
  });

  it('switches to offline when an offline event fires', () => {
    setOnLine(true);
    const { result } = renderHook(() => useNetworkStatus());

    act(() => {
      setOnLine(false);
      window.dispatchEvent(new Event('offline'));
    });

    expect(result.current.isOnline).toBe(false);
    expect(result.current.status).toBe('offline');
  });

  it('emits a transient reconnecting status then settles to online', () => {
    setOnLine(false);
    const { result } = renderHook(() => useNetworkStatus());
    expect(result.current.status).toBe('offline');

    act(() => {
      setOnLine(true);
      window.dispatchEvent(new Event('online'));
    });

    expect(result.current.isOnline).toBe(true);
    expect(result.current.status).toBe('reconnecting');

    act(() => {
      vi.advanceTimersByTime(2000);
    });

    expect(result.current.status).toBe('online');
  });
});
