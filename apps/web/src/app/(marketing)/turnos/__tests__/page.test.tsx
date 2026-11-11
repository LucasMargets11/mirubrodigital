import { readFileSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { formatPrice } from '@/lib/pricing/format';
import * as selectors from '@/lib/pricing/selectors';
import TurnosPage, { metadata } from '../page';

const pagePath = resolve(__dirname, '..', 'page.tsx');
const srcPath = resolve(__dirname, '..', '..', '..', '..');

function renderPage() {
  const html = renderToStaticMarkup(<TurnosPage />);
  return new DOMParser().parseFromString(html, 'text/html');
}

function localImportGraph(file: string, seen = new Map<string, string>()) {
  if (seen.has(file)) return seen;
  const source = readFileSync(file, 'utf8');
  seen.set(file, source);
  const ast = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true);
  if (/^['"]use client['"];/.test(source)) return seen;
  for (const statement of ast.statements) {
    if (
      !ts.isImportDeclaration(statement) ||
      statement.importClause?.isTypeOnly ||
      !ts.isStringLiteral(statement.moduleSpecifier)
    )
      continue;
    const specifier = statement.moduleSpecifier.text;
    if (!specifier.startsWith('@/') && !specifier.startsWith('.')) continue;
    const base = specifier.startsWith('@/')
      ? resolve(srcPath, specifier.slice(2))
      : resolve(dirname(file), specifier);
    const target = ['.ts', '.tsx', '\\index.ts', '\\index.tsx']
      .map((extension) => `${base}${extension}`)
      .find(existsSync);
    if (!target) throw new Error(`Cannot resolve ${specifier} from ${file}`);
    localImportGraph(target, seen);
  }
  return seen;
}

afterEach(() => vi.restoreAllMocks());

describe('/turnos public server landing', () => {
  it('renders the public demo server shell between steps and features without a session', () => {
    const doc = renderPage();
    const section = doc.querySelector('#recepcionista-ia')!;
    expect(section.textContent).toContain('Probá el Recepcionista IA');
    expect(section.textContent).toContain('Demo interactiva');
    expect(section.textContent).toContain('No se envían mensajes ni se guardan datos.');
    expect(section.querySelector('[data-testid="receptionist-sandbox"]')).not.toBeNull();
    expect(section.textContent).toContain('Conversación');
    expect(section.previousElementSibling?.textContent).toContain(
      'De la configuración a la reserva',
    );
    expect(section.nextElementSibling?.textContent).toContain('Una base común');
    expect(section.querySelectorAll('input, nav, form')).toHaveLength(0);
    expect(doc.body.textContent).toContain('Tu agenda, más ordenada.');
    expect(doc.querySelector('#planes-turnos')).not.toBeNull();
  });

  it('removes the authenticated sandbox route without an alias', () => {
    expect(existsSync(resolve(srcPath, 'app', 'app', 'turnos', 'recepcionista', 'page.tsx'))).toBe(
      false,
    );
  });

  it('exists in the marketing group and provides product metadata', () => {
    expect(existsSync(pagePath)).toBe(true);
    expect(metadata.title).toContain('MiRubro Turnos');
    expect(metadata.description).toBeTruthy();
    expect(metadata.alternates).toEqual({ canonical: 'https://www.mirubro.com/turnos' });
    expect(metadata.openGraph).toMatchObject({
      url: 'https://www.mirubro.com/turnos',
      type: 'website',
      locale: 'es_AR',
    });
    expect(metadata.twitter).toMatchObject({ card: 'summary_large_image' });
    expect(renderPage().querySelectorAll('h1')).toHaveLength(1);
  });

  it('renders all three canonical plans and their exact monthly and annual prices', () => {
    const doc = renderPage();
    const pricing = doc.querySelector('#planes-turnos')!;
    const plans = selectors.getPlansForVertical('appointments');
    expect(plans.map((plan) => plan.code)).toEqual([
      'appointments',
      'appointments_pro',
      'appointments_ai',
    ]);
    expect(pricing.querySelectorAll('h3')).toHaveLength(plans.length);
    for (const plan of plans) {
      expect(pricing.textContent).toContain(plan.name);
      expect(pricing.textContent).toContain(
        `${plan.professionalsIncluded} profesionales incluidos`,
      );
      expect(pricing.textContent).toContain(
        `${plan.secondaryUsersIncluded} usuarios secundarios incluidos`,
      );
      if (plan.pricingMode !== 'usage_tier') {
        expect(pricing.textContent).toContain(formatPrice(selectors.getPlanPrice(plan, 'monthly')));
        expect(pricing.textContent).toContain(
          `Pago anual: ${formatPrice(selectors.getPlanPrice(plan, 'yearly'))} ARS en total`,
        );
      }
    }
  });

  it('uses the pricing selectors rather than duplicated amounts or a calculated annual discount', () => {
    const canonicalGetPrice = selectors.getPlanPrice;
    vi.spyOn(selectors, 'getPlanPrice').mockImplementation(
      (plan, cycle, tier) => canonicalGetPrice(plan, cycle, tier) + (cycle === 'monthly' ? 17 : 31),
    );
    const text = renderPage().body.textContent!;
    for (const plan of selectors.getPlansForVertical('appointments')) {
      if (plan.pricingMode === 'usage_tier') continue;
      expect(text).toContain(formatPrice(canonicalGetPrice(plan, 'monthly') + 17));
      expect(text).toContain(formatPrice(canonicalGetPrice(plan, 'yearly') + 31));
    }
    const source = readFileSync(pagePath, 'utf8');
    const ast = ts.createSourceFile(pagePath, source, ts.ScriptTarget.Latest, true);
    function checkNumbers(node: ts.Node) {
      expect(ts.isNumericLiteral(node)).toBe(false);
      ts.forEachChild(node, checkNumbers);
    }
    checkNumbers(ast);
    expect(source).not.toMatch(/(?:\$|ARS)\s*\d|20%/);
  });

  it('shows canonical IA tiers as one complete plan, with custom as contact sales, never zero', () => {
    const doc = renderPage();
    const section = doc.querySelector('[aria-labelledby="turnos-ia-title"]')!;
    const ai = selectors.getPlan('appointments_ai')!;
    const rows = section.querySelectorAll('dl > div');
    expect(rows).toHaveLength(ai.usageTiers!.length);
    ai.usageTiers!.forEach((code, index) => {
      const tier = selectors.getUsageTier(code)!;
      const text = rows[index].textContent!;
      expect(text).toContain(tier.name);
      if (tier.purchaseMode === 'contact_sales') {
        expect(text).toContain('A medida');
        expect(text).toContain('equipo comercial');
        expect(text).not.toMatch(/\$|\b0\b|null/);
      } else {
        expect(text).toContain(
          `${tier.includedConversations.toLocaleString('es-AR')} sesiones / mes`,
        );
        expect(text).toContain(formatPrice(tier.monthlyPrice));
        expect(text).toContain(`Pago anual: ${formatPrice(tier.annualPrice)} ARS en total`);
      }
    });
    expect(section.textContent).toContain('No se suma el precio de Pro');
  });

  it('derives IA session quantities from usage tiers', () => {
    const canonicalGetTier = selectors.getUsageTier;
    vi.spyOn(selectors, 'getUsageTier').mockImplementation((code) => {
      const tier = canonicalGetTier(code);
      return tier?.purchaseMode === 'self_service'
        ? { ...tier, includedConversations: tier.includedConversations + 7 }
        : tier;
    });
    const text = renderPage().body.textContent!;
    for (const code of selectors.getPlan('appointments_ai')!.usageTiers!) {
      const tier = canonicalGetTier(code)!;
      if (tier.purchaseMode === 'self_service') {
        expect(text).toContain(
          `${(tier.includedConversations + 7).toLocaleString('es-AR')} sesiones / mes`,
        );
      }
    }
  });

  it('keeps the inactive product visible without purchase, checkout or subscription links', () => {
    expect(selectors.getProduct('appointments')?.is_active).toBe(false);
    const doc = renderPage();
    expect(doc.body.textContent).toContain('Próximamente disponible para contratación online');
    const links = Array.from(doc.querySelectorAll('a'));
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(['#planes-turnos', '/contacto']).toContain(link.getAttribute('href'));
      expect(link.textContent).not.toMatch(/comprar|contratar|checkout/i);
    }
    expect(doc.querySelectorAll('form, nav, footer')).toHaveLength(0);
    expect(doc.querySelector('#planes-turnos')).not.toBeNull();
    expect(doc.body.innerHTML).not.toContain('/pricing?service=appointments');
  });

  it('publishes SoftwareApplication without an invented offer', () => {
    const script = renderPage().querySelector('script[type="application/ld+json"]')!;
    const data = JSON.parse(script.textContent!);
    expect(data).toMatchObject({
      '@type': 'SoftwareApplication',
      name: 'MiRubro Turnos',
      url: 'https://www.mirubro.com/turnos',
    });
    expect(data).not.toHaveProperty('offers');
  });

  it('keeps the local import tree server-first and free of operational or heavy dependencies', () => {
    const graph = localImportGraph(pagePath);
    expect(graph.size).toBeGreaterThan(1);
    for (const [file, source] of graph) {
      if (/^['"]use client['"];/.test(source)) {
        expect(file).toBe(
          resolve(
            srcPath,
            'features',
            'appointments',
            'receptionist-sandbox',
            'receptionist-sandbox-loader.tsx',
          ),
        );
        expect(source).toContain('if (!nearViewport) return');
        expect(source).toContain('IntersectionObserver');
        expect(source).toContain("import('./receptionist-sandbox')");
        expect(source).not.toMatch(/getSession|useSession|fetch\s*\(|setInterval|WebSocket/);
        continue;
      }
      expect(source, file).not.toMatch(/['"]use client['"]/);
      expect(source, file).not.toMatch(/\bfetch\s*\(|\buseEffect\s*\(/);
      expect(source, file).not.toMatch(
        /from\s+['"][^'"]*(?:axios|react-query|swr|framer-motion|echarts|recharts|app\/app\/turnos|app\/t\/|calendar|ExpandingPanelSection)/i,
      );
      expect(source, file).not.toMatch(/\/api\/|\/checkout|\/subscribe/);
    }
    const pageSource = graph.get(pagePath)!;
    expect(pageSource).not.toMatch(/from ['"]@\/components\/marketing\/product-landing['"]/);
  });
});
