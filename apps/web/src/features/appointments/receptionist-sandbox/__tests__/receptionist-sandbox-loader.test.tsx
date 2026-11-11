import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ReceptionistSandboxLoader } from '../receptionist-sandbox-loader';
import { SandboxPlaceholder } from '../sandbox-placeholder';

let intersect: IntersectionObserverCallback;
const disconnect = vi.fn();
const observe = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      constructor(callback: IntersectionObserverCallback, options: IntersectionObserverInit) {
        intersect = callback;
        expect(options.rootMargin).toBe('300px');
      }
      observe = observe;
      disconnect = disconnect;
    },
  );
  Element.prototype.scrollTo = vi.fn();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('public sandbox lazy boundary', () => {
  it('keeps a static shell until near the viewport, then loads idle without auth or autoplay', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    render(<ReceptionistSandboxLoader placeholder={<SandboxPlaceholder />} />);
    expect(screen.getByText('Conversación')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Iniciar demo' })).not.toBeInTheDocument();
    act(() =>
      intersect(
        [{ isIntersecting: false } as IntersectionObserverEntry],
        {} as IntersectionObserver,
      ),
    );
    expect(screen.queryByRole('button', { name: 'Iniciar demo' })).not.toBeInTheDocument();
    act(() =>
      intersect(
        [{ isIntersecting: true } as IntersectionObserverEntry],
        {} as IntersectionObserver,
      ),
    );
    expect(disconnect).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Iniciar demo' })).toBeVisible());
    expect(screen.queryByText('Conversación')).not.toBeInTheDocument();
    expect(screen.queryByTestId('receptionist-message-bubble')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox')).toBeDisabled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('disconnects the viewport observer on unmount', () => {
    const { unmount } = render(<ReceptionistSandboxLoader placeholder={<SandboxPlaceholder />} />);
    expect(observe).toHaveBeenCalledOnce();
    unmount();
    expect(disconnect).toHaveBeenCalledOnce();
  });

  it('loads on browsers without IntersectionObserver', async () => {
    vi.stubGlobal('IntersectionObserver', undefined);
    render(<ReceptionistSandboxLoader placeholder={<SandboxPlaceholder />} />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Iniciar demo' })).toBeVisible());
  });
});
