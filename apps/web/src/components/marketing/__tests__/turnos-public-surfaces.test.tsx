import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { ProductsSection } from '../sections/products';
import { MarketingFooter } from '@/components/navigation/marketing-footer';
import HomePage from '@/app/(marketing)/page';
import ServicesPage, { metadata } from '@/app/(marketing)/services/page';
import NosotrosPage from '@/app/(marketing)/nosotros/page';
import { PRODUCT_CARDS } from '@/app/(marketing)/nosotros/_data';
import { FAQ_DATA } from '@/app/(marketing)/preguntas-frecuentes/_data';
import sitemap from '@/app/sitemap';
import { getProduct } from '@/lib/pricing/selectors';

vi.mock('@/components/marketing/sections/blog-resources', () => ({
  BlogResourcesSection: () => null,
}));
vi.mock('@/app/(marketing)/blog/_api', () => ({
  getBlogSitemapEntries: vi.fn().mockResolvedValue([{ slug: 'example' }]),
}));

function documentFor(element: ReactElement) {
  return new DOMParser().parseFromString(renderToStaticMarkup(element), 'text/html');
}

describe('TURNOS PUBLIC 02 static surfaces', () => {
  it('renders exactly one Turnos card in the existing home product list', () => {
    const doc = documentFor(<ProductsSection />);
    expect(doc.querySelectorAll('h3')).toHaveLength(4);
    const cards = doc.querySelectorAll('a[href="/turnos"]');
    expect(cards).toHaveLength(1);
    const card = cards[0];
    expect(card.querySelector('h3')?.textContent).toBe('Turnos');
    expect(card.textContent).toContain('Conocer Turnos');
    expect(card.querySelectorAll('li')).toHaveLength(3);
    expect(card.querySelectorAll('button, a, form')).toHaveLength(0);
    expect(card.textContent).not.toMatch(/comprar|contratar|checkout|suscrib|ARS|\$\s*\d/i);
    expect(doc.body.textContent).not.toMatch(/(?:tres|3) soluciones/i);
    expect(documentFor(<HomePage />).querySelectorAll('#productos a[href="/turnos"]')).toHaveLength(
      1,
    );
  });

  it('adds an ordinary product link to the marketing footer', () => {
    const doc = documentFor(<MarketingFooter />);
    const products = Array.from(doc.querySelectorAll('h4')).find(
      (heading) => heading.textContent === 'Productos',
    )?.parentElement;
    expect(products?.querySelectorAll('a[href="/turnos"]')).toHaveLength(1);
    expect(products?.querySelector('a[href="/turnos"]')?.textContent).toBe('Turnos');
  });

  it('adds Turnos to services without pricing, checkout or purchase CTAs', () => {
    const doc = documentFor(<ServicesPage />);
    const section = doc.querySelector('section#turnos')!;
    expect(section.querySelector('h2')?.textContent).toBe('Turnos');
    expect(section.querySelectorAll('h3').length).toBeGreaterThan(0);
    expect(section.textContent).toMatch(/agenda.*profesionales.*clientes.*reservas/i);
    expect(section.textContent).toContain('según el plan');
    expect(section.querySelectorAll('a')).toHaveLength(1);
    expect(section.querySelector('a')?.getAttribute('href')).toBe('/turnos');
    expect(section.querySelector('a')?.textContent).toBe('Conocer Turnos');
    expect(section.textContent).not.toMatch(
      /ver planes|comprar|contratar|checkout|suscrib|ARS|\$\s*\d/i,
    );
    expect(metadata.description).toContain('Turnos');
    expect(doc.querySelector('a[href="/pricing?service=commerce"]')).not.toBeNull();
  });

  it('renders Turnos on nosotros with its own icon, even when cards are reordered', () => {
    const card = PRODUCT_CARDS.find((entry) => entry.title === 'Turnos')!;
    expect(card.icon).toBeDefined();
    expect(
      PRODUCT_CARDS.every(
        (entry) => typeof entry.icon === 'object' || typeof entry.icon === 'function',
      ),
    ).toBe(true);
    PRODUCT_CARDS.reverse();
    try {
      const doc = documentFor(<NosotrosPage />);
      const heading = Array.from(doc.querySelectorAll('h3')).filter(
        (entry) => entry.textContent === 'Turnos',
      );
      expect(heading).toHaveLength(1);
      expect(heading[0].parentElement?.querySelector('svg')?.innerHTML).toBe(
        documentFor(<card.icon />).querySelector('svg')?.innerHTML,
      );
    } finally {
      PRODUCT_CARDS.reverse();
    }
  });

  it('lists the landing once in sitemap with the same product priority and frequency', async () => {
    const entries = await sitemap();
    const turnos = entries.filter((entry) => entry.url === 'https://www.mirubro.com/turnos');
    expect(turnos).toHaveLength(1);
    for (const product of ['gestion', 'carta', 'resenas']) {
      const entry = entries.find((item) => item.url === `https://www.mirubro.com/${product}`)!;
      expect(turnos[0]).toMatchObject({
        changeFrequency: entry.changeFrequency,
        priority: entry.priority,
      });
    }
    expect(entries.some((entry) => entry.url.endsWith('/blog/example'))).toBe(true);
    expect(entries.some((entry) => entry.url.includes('/t/'))).toBe(false);
  });

  it('corrects the existing complete-offering FAQ copy without adding a product FAQ', () => {
    const general = FAQ_DATA.find((category) => category.category === 'General')!;
    for (const question of ['¿Qué es Mi Rubro?', '¿Qué herramientas ofrece actualmente?']) {
      const answer = general.items.find((item) => item.question === question)!.answer;
      expect(answer).toContain('Turnos');
      expect(answer).not.toMatch(/(?:tres|3) soluciones/i);
    }
    expect(FAQ_DATA.find((category) => category.category === 'Productos')?.items).toHaveLength(3);
  });

  it('keeps appointments inactive and every new Turnos link informational', () => {
    expect(getProduct('appointments')?.is_active).toBe(false);
    for (const Component of [HomePage, ServicesPage, MarketingFooter]) {
      const doc = documentFor(<Component />);
      expect(doc.querySelector('a[href="/pricing?service=appointments"]')).toBeNull();
      const links = Array.from(doc.querySelectorAll('a')).filter((link) =>
        /Turnos/.test(link.textContent ?? ''),
      );
      expect(links.length).toBeGreaterThan(0);
      for (const link of links) expect(link.getAttribute('href')).toBe('/turnos');
    }
  });

  it('adds only static content to server surfaces, with no fetches or heavy imports', () => {
    const src = resolve(__dirname, '..', '..', '..');
    const files = [
      'components/marketing/sections/products.tsx',
      'components/navigation/marketing-footer.tsx',
      'app/sitemap.ts',
      'app/(marketing)/page.tsx',
      'app/(marketing)/services/page.tsx',
      'app/(marketing)/nosotros/_data.ts',
      'app/(marketing)/nosotros/_components/AboutProductsSection.tsx',
      'app/(marketing)/contacto/_constants.ts',
      'app/(marketing)/contacto/_components/ContactTopics.tsx',
      'app/(marketing)/soporte/_constants.ts',
      'app/(marketing)/soporte/_components/SupportTopics.tsx',
      'app/(marketing)/preguntas-frecuentes/_data.ts',
    ];
    for (const file of files) {
      const source = readFileSync(resolve(src, file), 'utf8');
      expect(source, file).not.toMatch(/['"]use client['"]|\bfetch\s*\(|\bimport\s*\(/);
      expect(source, file).not.toMatch(
        /from ['"](?:@tanstack\/react-query|framer-motion|next\/dynamic)/,
      );
    }
    const nav = readFileSync(resolve(src, 'components/navigation/marketing-nav.tsx'), 'utf8');
    expect(nav.match(/\buseState\s*\(/g)).toHaveLength(1);
    expect(nav).not.toMatch(/\bfetch\s*\(|\bimport\s*\(/);
  });
});
