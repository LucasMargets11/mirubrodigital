import Link from 'next/link';
import { QrCode } from 'lucide-react';

import { Button } from '@/components/ui/button';

import { useBundles } from '../api';
import { BillingVertical, Bundle } from '../types';

interface PlansBundlesProps {
  vertical: BillingVertical;
  billingPeriod: 'monthly' | 'yearly';
  onChooseBundle: (bundle: Bundle) => void;
}

export function PlansBundles({ vertical, billingPeriod, onChooseBundle }: PlansBundlesProps) {
  const { data: bundles, isLoading } = useBundles(vertical);

  if (isLoading) return <div>Cargando packs...</div>;

  if (!bundles?.length) {
    if (vertical === 'menu_qr') {
      return <MenuQrPlaceholder />;
    }

    return <div className="text-center text-slate-500">No hay packs disponibles para esta vertical.</div>;
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-stretch">
      {bundles.map((bundle) => {
        const price =
          billingPeriod === 'monthly'
            ? bundle.fixed_price_monthly
            : bundle.fixed_price_yearly ?? (bundle.fixed_price_monthly || 0) * 12;

        // Determinar características según el plan
        const planFeatures = getPlanFeatures(bundle.code, vertical);

        return (
          <div
            key={bundle.code}
            className={`h-full border rounded-2xl bg-white shadow-sm hover:shadow-lg transition-all ${
              bundle.is_default_recommended 
                ? 'border-brand-500 ring-2 ring-brand-500 scale-[1.02]' 
                : 'border-slate-200'
            }`}
          >
            <div className="h-full flex flex-col p-6">
              {/* Badge con espacio reservado arriba */}
              <div className="min-h-[20px] mb-2">
                {bundle.badge && (
                  <span className="inline-block bg-brand-500 text-white text-xs font-bold px-3 py-1 rounded-full shadow-md">
                    {bundle.badge}
                  </span>
                )}
              </div>
              
              {/* Header */}
              <div className="mb-4">
                <h3 className="text-2xl font-bold mb-2 text-slate-900">{bundle.name}</h3>
                <p className="text-slate-600 text-sm min-h-[40px]">{bundle.description}</p>
              </div>

              {/* Precio */}
              <div className="mb-6">
                <div className="flex items-baseline">
                  <span className="text-4xl font-bold text-slate-900">
                    ${((price ?? 0) / 100).toFixed(0)}
                  </span>
                  <span className="text-slate-500 text-sm ml-2">
                    / {billingPeriod === 'monthly' ? 'mes' : 'año'}
                  </span>
                </div>
                {billingPeriod === 'yearly' && (
                  <p className="text-green-600 text-xs font-semibold mt-1">
                    Ahorrás 20% vs mensual
                  </p>
                )}
              </div>

              {/* Meta bullets */}
              {planFeatures && (
                <div className="mb-4 pb-4 border-b border-slate-100">
                  <div className="space-y-2 text-sm">
                    {planFeatures.branches && (
                      <div className="flex items-center text-slate-700">
                        <span className="mr-2 text-brand-500 font-bold">🏪</span>
                        <span>{planFeatures.branches}</span>
                      </div>
                    )}
                    {planFeatures.users && (
                      <div className="flex items-center text-slate-700">
                        <span className="mr-2 text-brand-500 font-bold">👥</span>
                        <span>{planFeatures.users}</span>
                      </div>
                    )}
                    {planFeatures.highlight && (
                      <div className="flex items-center text-slate-700 font-semibold">
                        <span className="mr-2 text-brand-500">✨</span>
                        <span>{planFeatures.highlight}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Checklist de módulos */}
              <ul className="space-y-2 flex-1">
                {getKeyModules(bundle.modules, bundle.code).map((m) => (
                  <li key={m.code} className="flex items-start text-sm text-slate-700">
                    <span className="mr-2 text-green-500 font-bold">✓</span>
                    <span>{m.name}</span>
                  </li>
                ))}
              </ul>

              {/* Footer CTA alineado */}
              <div className="mt-auto pt-6">
                <button
                  onClick={() => onChooseBundle(bundle)}
                  className={`w-full py-3 px-4 rounded-lg font-semibold transition-all ${
                    bundle.is_default_recommended
                      ? 'bg-brand-600 text-white hover:bg-brand-700 shadow-md'
                      : 'bg-slate-100 text-slate-900 hover:bg-slate-200'
                  }`}
                >
                  Elegir {bundle.name}
                </button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Helper para obtener características específicas de cada plan
function getPlanFeatures(bundleCode: string, vertical: BillingVertical) {
  if (vertical !== 'commercial') return null;

  const features: Record<string, { branches: string; users?: string; highlight?: string }> = {
    gestion_start: {
      branches: '1 sucursal',
      users: 'Usuarios ilimitados',
      highlight: 'Ideal para empezar'
    },
    gestion_pro: {
      branches: 'Hasta 3 sucursales',
      users: 'Usuarios ilimitados',
      highlight: 'Incluye Tesorería'
    },
    gestion_business: {
      branches: 'Hasta 5 sucursales',
      users: 'Usuarios ilimitados',
      highlight: 'Facturación incluida'
    }
  };

  return features[bundleCode] || null;
}

// Helper para mostrar solo los módulos más relevantes (max 6)
function getKeyModules(modules: any[], bundleCode: string) {
  const priorityModules = [
    'gestion_products',
    'gestion_customers',
    'gestion_cash',
    'gestion_treasury',
    'gestion_invoices',
    'gestion_reports',
    'gestion_multi_branch',
    'gestion_inventory_advanced'
  ];

  // Ordenar por prioridad y tomar los primeros 6
  const sorted = modules.sort((a, b) => {
    const aIndex = priorityModules.indexOf(a.code);
    const bIndex = priorityModules.indexOf(b.code);
    if (aIndex === -1 && bIndex === -1) return 0;
    if (aIndex === -1) return 1;
    if (bIndex === -1) return -1;
    return aIndex - bIndex;
  });

  return sorted.slice(0, 6);
}

function MenuQrPlaceholder() {
  return (
    <div className="mx-auto max-w-3xl rounded-3xl border border-dashed border-brand-200 bg-white/90 p-10 text-center shadow-lg shadow-slate-100">
      <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
        <QrCode className="h-8 w-8" aria-hidden="true" />
      </div>
      <h3 className="text-2xl font-semibold text-slate-900">Planes en preparación</h3>
      <p className="mt-2 text-base text-slate-600">
        Estamos terminando los packs comerciales para Menú QR Online. Mientras tanto coordinamos la implementación con nuestro equipo.
      </p>
      <Button asChild className="mt-6 bg-brand-600 text-white hover:bg-brand-700">
        <Link href="/subscribe?service=menu_qr">Consultar</Link>
      </Button>
    </div>
  );
}
