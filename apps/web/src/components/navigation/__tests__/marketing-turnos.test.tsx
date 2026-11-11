import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MarketingNav } from '../marketing-nav';

vi.mock('next/navigation', () => ({ usePathname: () => '/' }));
vi.mock('@/hooks/use-scroll-direction', () => ({
  useScrollDirection: () => ({ scrollDir: 'up', isAtTop: true }),
}));

afterEach(cleanup);

describe('Turnos marketing navigation', () => {
  it('shares the product destination between desktop and mobile', () => {
    const { container } = render(<MarketingNav />);
    const desktop = within(container.querySelector('nav')!);
    expect(desktop.getByRole('link', { name: 'Turnos' })).toHaveAttribute('href', '/turnos');
    const links = container.querySelectorAll('a[href="/turnos"]');
    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link.textContent).toBe('Turnos');
      expect(link.querySelector('button')).toBeNull();
    }
    expect(container.querySelector('a[href="/pricing?service=appointments"]')).toBeNull();
  });

  it('preserves opening, scroll locking and closing when the mobile product is chosen', () => {
    const { container } = render(<MarketingNav />);
    fireEvent.click(screen.getByRole('button', { name: 'Abrir menú' }));
    expect(screen.getByRole('button', { name: 'Cerrar menú' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    expect(document.body.style.overflow).toBe('hidden');
    const mobile = Array.from(container.querySelectorAll('a[href="/turnos"]')).find(
      (link) => !link.closest('nav'),
    )!;
    mobile.addEventListener('click', (event) => event.preventDefault(), { once: true });
    fireEvent.click(mobile);
    expect(screen.getByRole('button', { name: 'Abrir menú' })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(document.body.style.overflow).toBe('');
  });
});
