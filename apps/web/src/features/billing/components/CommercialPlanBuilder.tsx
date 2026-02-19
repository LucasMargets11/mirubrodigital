import { useState, useEffect } from 'react';
import { useBundles } from '../api';
import { Bundle } from '../types';
import { Minus, Plus } from 'lucide-react';

interface CommercialPlanBuilderProps {
  billingPeriod: 'monthly' | 'yearly';
  onSubscribe: (config: PlanConfig) => void;
  onCancel: () => void;
}

interface PlanConfig {
  bundleCode: string;
  bundleName: string;
  branches: number;
  users: number;
  addInvoicing: boolean;
  totalPrice: number;
}

const PLAN_LIMITS = {
  gestion_start: { minBranches: 1, maxBranches: 1, includedBranches: 1, allowInvoicing: false },
  gestion_pro: { minBranches: 1, maxBranches: 3, includedBranches: 1, allowInvoicing: true },
  gestion_business: { minBranches: 1, maxBranches: 20, includedBranches: 5, allowInvoicing: false }, // ilimitadas, pero ponemos 20 como UI max
};

const ADDON_PRICES = {
  extra_branch: { monthly: 5000, yearly: 48000 }, // $50/mes
  invoicing_module: { monthly: 15000, yearly: 144000 }, // $150/mes
};

export function CommercialPlanBuilder({ billingPeriod, onSubscribe, onCancel }: CommercialPlanBuilderProps) {
  const { data: bundles, isLoading } = useBundles('commercial');
  
  const [selectedBundle, setSelectedBundle] = useState<Bundle | null>(null);
  const [branches, setBranches] = useState(1);
  const [users, setUsers] = useState(3);
  const [addInvoicing, setAddInvoicing] = useState(false);

  useEffect(() => {
    if (bundles && bundles.length > 0 && !selectedBundle) {
      // Seleccionar PRO por defecto (recomendado)
      const proPlan = bundles.find(b => b.code === 'gestion_pro') || bundles[0];
      setSelectedBundle(proPlan);
      setBranches(1);
    }
  }, [bundles, selectedBundle]);

  const handlePlanChange = (bundle: Bundle) => {
    setSelectedBundle(bundle);
    const limits = PLAN_LIMITS[bundle.code as keyof typeof PLAN_LIMITS];
    if (limits) {
      setBranches(limits.includedBranches);
      if (!limits.allowInvoicing) {
        setAddInvoicing(false);
      }
    }
  };

  const calculateTotal = (): number => {
    if (!selectedBundle) return 0;

    const basePeriodKey = billingPeriod === 'monthly' ? 'fixed_price_monthly' : 'fixed_price_yearly';
    let total = selectedBundle[basePeriodKey] || 0;

    const limits = PLAN_LIMITS[selectedBundle.code as keyof typeof PLAN_LIMITS];
    if (limits) {
      const extraBranches = Math.max(0, branches - limits.includedBranches);
      const branchPrice = ADDON_PRICES.extra_branch[billingPeriod];
      total += extraBranches * branchPrice;
    }

    if (addInvoicing && selectedBundle.code === 'gestion_pro') {
      total += ADDON_PRICES.invoicing_module[billingPeriod];
    }

    return total;
  };

  const handleConfirm = () => {
    if (!selectedBundle) return;

    const config: PlanConfig = {
      bundleCode: selectedBundle.code,
      bundleName: selectedBundle.name,
      branches,
      users,
      addInvoicing,
      totalPrice: calculateTotal(),
    };

    onSubscribe(config);
  };

  if (isLoading) {
    return <div className="text-center py-12">Cargando planes...</div>;
  }

  if (!bundles || bundles.length === 0) {
    return <div className="text-center py-12 text-slate-500">No hay planes disponibles</div>;
  }

  const limits = selectedBundle ? PLAN_LIMITS[selectedBundle.code as keyof typeof PLAN_LIMITS] : null;
  const total = calculateTotal();

  return (
    <div className="bg-white rounded-2xl shadow-xl max-w-5xl mx-auto overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-brand-600 to-brand-500 p-6 text-white">
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-2xl font-bold">Armá tu plan ideal</h2>
            <p className="text-brand-100 text-sm mt-1">Configurá tu plan según tus necesidades</p>
          </div>
          <button
            onClick={onCancel}
            className="text-white hover:bg-white/20 rounded-full p-2 transition-colors"
          >
            ✕
          </button>
        </div>
      </div>

      <div className="p-8">
        {/* Plan Selection */}
        <div className="mb-8">
          <h3 className="text-lg font-semibold text-slate-900 mb-4">1. Elegí tu plan base</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {bundles.map((bundle) => {
              const isSelected = selectedBundle?.code === bundle.code;
              const price = billingPeriod === 'monthly' ? bundle.fixed_price_monthly : bundle.fixed_price_yearly;

              return (
                <button
                  key={bundle.code}
                  onClick={() => handlePlanChange(bundle)}
                  className={`p-4 rounded-xl border-2 text-left transition-all ${
                    isSelected
                      ? 'border-brand-500 bg-brand-50 shadow-md'
                      : 'border-slate-200 hover:border-brand-300 hover:bg-slate-50'
                  }`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <h4 className="font-bold text-slate-900">{bundle.name}</h4>
                    {bundle.badge && (
                      <span className="text-xs bg-brand-500 text-white px-2 py-0.5 rounded-full">
                        {bundle.badge}
                      </span>
                    )}
                  </div>
                  <p className="text-2xl font-bold text-slate-900">
                    ${((price || 0) / 100).toFixed(0)}
                    <span className="text-sm font-normal text-slate-500">/{billingPeriod === 'monthly' ? 'mes' : 'año'}</span>
                  </p>
                  <p className="text-xs text-slate-600 mt-2">{bundle.description}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Branch Configuration */}
        {selectedBundle && limits && (
          <div className="mb-8 pb-8 border-b border-slate-200">
            <h3 className="text-lg font-semibold text-slate-900 mb-4">2. Configurá tus sucursales</h3>
            
            <div className="bg-slate-50 rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <p className="font-semibold text-slate-900">Número de sucursales</p>
                  <p className="text-sm text-slate-600">
                    {limits.includedBranches} {limits.includedBranches === 1 ? 'incluida' : 'incluidas'} en el plan
                    {branches > limits.includedBranches && (
                      <span className="text-brand-600 font-medium">
                        {' '}+ {branches - limits.includedBranches} extra{branches - limits.includedBranches > 1 ? 's' : ''}
                      </span>
                    )}
                  </p>
                </div>

                <div className="flex items-center space-x-4">
                  <button
                    onClick={() => setBranches(Math.max(limits.minBranches, branches - 1))}
                    disabled={branches <= limits.minBranches}
                    className="w-10 h-10 flex items-center justify-center rounded-lg border-2 border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  >
                    <Minus className="w-4 h-4" />
                  </button>

                  <span className="text-3xl font-bold text-slate-900 w-12 text-center">
                    {branches}
                  </span>

                  <button
                    onClick={() => setBranches(Math.min(limits.maxBranches, branches + 1))}
                    disabled={branches >= limits.maxBranches}
                    className="w-10 h-10 flex items-center justify-center rounded-lg border-2 border-brand-500 bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {branches > limits.includedBranches && (
                <div className="bg-white rounded-lg p-3 border border-brand-200">
                  <p className="text-sm text-slate-700">
                    <span className="font-semibold text-brand-600">
                      {branches - limits.includedBranches} sucursal{branches - limits.includedBranches > 1 ? 'es' : ''} adicional{branches - limits.includedBranches > 1 ? 'es' : ''}:
                    </span>
                    {' '}${(((branches - limits.includedBranches) * ADDON_PRICES.extra_branch[billingPeriod]) / 100).toFixed(0)}
                    /{billingPeriod === 'monthly' ? 'mes' : 'año'}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Invoicing Add-on (only for PRO) */}
        {selectedBundle?.code === 'gestion_pro' && (
          <div className="mb-8 pb-8 border-b border-slate-200">
            <h3 className="text-lg font-semibold text-slate-900 mb-4">3. Add-ons opcionales</h3>
            
            <div className="bg-slate-50 rounded-xl p-6">
              <label className="flex items-start cursor-pointer">
                <input
                  type="checkbox"
                  checked={addInvoicing}
                  onChange={(e) => setAddInvoicing(e.target.checked)}
                  className="mt-1 w-5 h-5 text-brand-600 rounded border-slate-300 focus:ring-brand-500"
                />
                <div className="ml-4 flex-1">
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="font-semibold text-slate-900">Módulo de Facturación Electrónica</p>
                      <p className="text-sm text-slate-600 mt-1">
                        Emisión de facturas fiscales, gestión de series y timbrado
                      </p>
                    </div>
                    <span className="text-lg font-bold text-slate-900 ml-4">
                      +${(ADDON_PRICES.invoicing_module[billingPeriod] / 100).toFixed(0)}
                    </span>
                  </div>
                  {addInvoicing && (
                    <div className="mt-3 bg-green-50 border border-green-200 rounded-lg p-3">
                      <p className="text-sm text-green-800">
                        ✓ Módulo agregado a tu plan
                      </p>
                    </div>
                  )}
                </div>
              </label>
            </div>
          </div>
        )}

        {/* Business includes invoicing */}
        {selectedBundle?.code === 'gestion_business' && (
          <div className="mb-8 pb-8 border-b border-slate-200">
            <h3 className="text-lg font-semibold text-slate-900 mb-4">3. Módulos incluidos</h3>
            
            <div className="bg-green-50 rounded-xl p-6 border border-green-200">
              <div className="flex items-start">
                <span className="text-2xl mr-3">✓</span>
                <div>
                  <p className="font-semibold text-green-900">Facturación Electrónica Incluida</p>
                  <p className="text-sm text-green-700 mt-1">
                    El plan Business incluye el módulo completo de facturación sin costo adicional
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Summary & CTA */}
        <div className="bg-gradient-to-br from-slate-50 to-slate-100 rounded-xl p-6">
          <div className="flex justify-between items-center mb-6">
            <div>
              <p className="text-sm text-slate-600">Total a pagar</p>
              <p className="text-4xl font-bold text-slate-900">
                ${(total / 100).toFixed(0)}
                <span className="text-lg text-slate-600 font-normal">
                  /{billingPeriod === 'monthly' ? 'mes' : 'año'}
                </span>
              </p>
              {billingPeriod === 'yearly' && (
                <p className="text-sm text-green-600 font-semibold mt-1">
                  Ahorrás 20% con facturación anual
                </p>
              )}
            </div>

            <button
              onClick={handleConfirm}
              className="px-8 py-4 bg-brand-600 text-white rounded-xl font-bold text-lg hover:bg-brand-700 shadow-lg hover:shadow-xl transition-all transform hover:scale-105 active:scale-95"
            >
              Confirmar Plan
            </button>
          </div>

          <div className="text-xs text-slate-500 space-y-1">
            <p>• Usuarios ilimitados en todos los planes</p>
            <p>• Cancelación en cualquier momento</p>
            <p>• Soporte técnico incluido</p>
          </div>
        </div>
      </div>
    </div>
  );
}
