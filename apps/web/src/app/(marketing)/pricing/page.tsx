'use client';

import { useState } from 'react';
import { PlansBundles } from '@/features/billing/components/PlansBundles';
import { PlansBuilderWizard } from '@/features/billing/components/PlansBuilderWizard';
import { Bundle, QuoteResponse } from '@/features/billing/types';
import { useRouter } from 'next/navigation';

export default function PricingPage() {
  const router = useRouter();
  const [vertical, setVertical] = useState<'commercial' | 'restaurant'>('commercial'); 
  const [billingPeriod, setBillingPeriod] = useState<'monthly' | 'yearly'>('monthly');
  const [mode, setMode] = useState<'packs' | 'custom'>('packs');
  
  const handleSubscribeBundle = (bundle: Bundle) => {
      // Logic for public site: Redirect to registration with plan params
      const params = new URLSearchParams({
          plan_code: bundle.code,
          billing_period: billingPeriod,
          vertical
      });
      router.push(`/subscribe?${params.toString()}`);
  };
  
  const handleSubscribeCustom = (selectedModules: string[], quote: QuoteResponse) => {
      // Logic for public site: Redirect to registration with custom params
      const params = new URLSearchParams({
          plan_code: 'custom',
          modules: selectedModules.join(','),
          billing_period: billingPeriod,
          vertical
      });
      router.push(`/subscribe?${params.toString()}`);
  };

  return (
    <div className="py-20 px-4 md:px-8 max-w-7xl mx-auto">
      <div className="text-center mb-16 space-y-4">
          <p className="text-sm font-semibold text-brand-600 uppercase tracking-wider">Planes Flexibles</p>
          <h1 className="text-4xl md:text-5xl font-display font-bold text-slate-900">
             Elige tu próximo nivel
          </h1>
          <p className="text-xl text-slate-600 max-w-2xl mx-auto">
             Escala de marketing a operaciones sin migraciones dolorosas. Precios transparentes que crecen con vos.
          </p>
      </div>

      <div className="flex flex-col items-center mb-12 space-y-6">
        {/* Vertical Selector (Simplified for demo) */}
        <div className="inline-flex rounded-lg border border-slate-200 p-1 bg-white shadow-sm">
             <button
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${vertical === 'commercial' ? 'bg-brand-50 text-brand-700' : 'text-slate-500 hover:text-slate-700'}`}
                onClick={() => setVertical('commercial')}
            >
                Comercios
            </button>
            <button
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${vertical === 'restaurant' ? 'bg-brand-50 text-brand-700' : 'text-slate-500 hover:text-slate-700'}`}
                onClick={() => setVertical('restaurant')}
            >
                Restaurantes
            </button>
        </div>

        {/* Billing Period Toggle */}
        <div className="bg-slate-100 p-1 rounded-lg flex shrink-0">
            <button
                className={`px-6 py-2 rounded-md text-sm font-medium transition-all ${billingPeriod === 'monthly' ? 'bg-white shadow text-slate-900' : 'text-slate-500'}`}
                onClick={() => setBillingPeriod('monthly')}
            >
                Mensual
            </button>
            <button
                className={`px-6 py-2 rounded-md text-sm font-medium transition-all ${billingPeriod === 'yearly' ? 'bg-white shadow text-slate-900' : 'text-slate-500'}`}
                onClick={() => setBillingPeriod('yearly')}
            >
                Anual <span className="text-green-600 text-xs ml-1 font-bold">-20%</span>
            </button>
        </div>
      </div>

      <div className="mb-12">
        <div className="flex justify-center space-x-12 border-b border-slate-200">
            <button 
                className={`pb-4 border-b-2 font-medium text-lg transition-colors px-4 ${mode === 'packs' ? 'border-brand-600 text-brand-600' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
                onClick={() => setMode('packs')}
            >
                Packs Recomendados
            </button>
            <button 
                className={`pb-4 border-b-2 font-medium text-lg transition-colors px-4 ${mode === 'custom' ? 'border-brand-600 text-brand-600' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
                onClick={() => setMode('custom')}
            >
                Armá tu plan
            </button>
        </div>
      </div>

      {mode === 'packs' && (
        <PlansBundles 
            vertical={vertical} 
            billingPeriod={billingPeriod} 
            onChooseBundle={handleSubscribeBundle}
        />
      )}

      {mode === 'custom' && (
         <div className="animate-in fade-in zoom-in duration-300">
             <PlansBuilderWizard
                vertical={vertical}
                billingPeriod={billingPeriod}
                onSubscribe={handleSubscribeCustom}
                onCancel={() => setMode('packs')}
            />
         </div>
      )}
    </div>
  );
}
