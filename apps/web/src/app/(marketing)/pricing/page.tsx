'use client';

import { useEffect, useState } from 'react';
import { PlansBundles } from '@/features/billing/components/PlansBundles';
import { PlansBuilderWizard } from '@/features/billing/components/PlansBuilderWizard';
import { CommercialPlanBuilder } from '@/features/billing/components/CommercialPlanBuilder';
import type { BillingVertical, Bundle, QuoteResponse } from '@/features/billing/types';
import { useRouter, useSearchParams } from 'next/navigation';
import { QrCode, Store, UtensilsCrossed, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

type VerticalOption = BillingVertical;

type ServiceOption = {
    key: VerticalOption;
    label: string;
    icon: LucideIcon;
    queryValue: string;
    description: string;
};

const SERVICE_OPTIONS: ServiceOption[] = [
    {
        key: 'commercial',
        label: 'Gestión Comercial',
        icon: Store,
        queryValue: 'commerce',
        description: 'Inventario, ventas y caja para retail'
    },
    {
        key: 'restaurant',
        label: 'Restaurantes',
        icon: UtensilsCrossed,
        queryValue: 'restaurant',
        description: 'Órdenes, mapa de mesas y cocina'
    },
    {
        key: 'menu_qr',
        label: 'Menú QR Online',
        icon: QrCode,
        queryValue: 'menu_qr',
        description: 'Carta digital editable y branding'
    }
];

const DEFAULT_VERTICAL: VerticalOption = 'commercial';

const QUERY_TO_VERTICAL = SERVICE_OPTIONS.reduce<Record<string, VerticalOption>>((acc, option) => {
    acc[option.queryValue] = option.key;
    return acc;
}, {} as Record<string, VerticalOption>);

const resolveVerticalFromQuery = (param: string | null): VerticalOption | null => {
    if (!param) {
        return null;
    }

    return QUERY_TO_VERTICAL[param] ?? null;
};

export default function PricingPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const [vertical, setVertical] = useState<VerticalOption>(() => resolveVerticalFromQuery(searchParams.get('service')) ?? DEFAULT_VERTICAL);
    const [billingPeriod, setBillingPeriod] = useState<'monthly' | 'yearly'>('monthly');
    const [mode, setMode] = useState<'packs' | 'custom'>('packs');

    const serviceParam = searchParams.get('service');

    useEffect(() => {
        const nextVertical = resolveVerticalFromQuery(serviceParam);
        if (nextVertical) {
            setVertical(nextVertical);
        }
    }, [serviceParam]);

    const handleSubscribeBundle = (bundle: Bundle) => {
        // Logic for public site: Redirect to registration with plan params
        const params = new URLSearchParams({
            plan_code: bundle.code,
            billing_period: billingPeriod,
            vertical
        });
        router.push(`/subscribe?${params.toString()}`);
    };

    const handleSubscribeCustom = (config: any) => {
        // Logic for public site: Redirect to registration with custom params
        const params = new URLSearchParams({
            plan_code: config.bundleCode || 'custom',
            billing_period: billingPeriod,
            vertical,
            branches: config.branches?.toString() || '1',
            add_invoicing: config.addInvoicing ? 'true' : 'false',
        });
        router.push(`/subscribe?${params.toString()}`);
    };

    return (
        <div className="bg-white min-h-screen">
            <div className="py-20 px-6 max-w-6xl mx-auto">
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
                <ServiceSelectorCards value={vertical} onChange={setVertical} options={SERVICE_OPTIONS} />

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
                    {vertical === 'commercial' ? (
                        <CommercialPlanBuilder
                            billingPeriod={billingPeriod}
                            onSubscribe={handleSubscribeCustom}
                            onCancel={() => setMode('packs')}
                        />
                    ) : (
                        <PlansBuilderWizard
                            vertical={vertical}
                            billingPeriod={billingPeriod}
                            onSubscribe={(modules, quote) => handleSubscribeCustom({ modules, quote })}
                            onCancel={() => setMode('packs')}
                        />
                    )}
                </div>
            )}
            </div>
        </div>
    );
}

type ServiceSelectorCardsProps = {
    value: VerticalOption;
    onChange: (nextValue: VerticalOption) => void;
    options: ServiceOption[];
};

function ServiceSelectorCards({ value, onChange, options }: ServiceSelectorCardsProps) {
    return (
        <div className="w-full flex justify-center">
            <div className="grid w-full max-w-3xl grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {options.map((service) => (
                    <ServiceCardOption
                        key={service.key}
                        option={service}
                        isSelected={value === service.key}
                        onSelect={onChange}
                    />
                ))}
            </div>
        </div>
    );
}

type ServiceCardOptionProps = {
    option: ServiceOption;
    isSelected: boolean;
    onSelect: (key: VerticalOption) => void;
};

function ServiceCardOption({ option, isSelected, onSelect }: ServiceCardOptionProps) {
    const Icon = option.icon;

    return (
        <button
            type="button"
            role="button"
            aria-pressed={isSelected}
            onClick={() => onSelect(option.key)}
            className={cn(
                'h-full w-full rounded-2xl border bg-white p-5 sm:p-6 flex flex-col items-center text-center gap-3 transition-all duration-200 hover:border-brand-300 hover:bg-brand-50/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2',
                isSelected
                    ? 'border-brand-500 bg-brand-50 text-brand-700 shadow-lg ring-2 ring-brand-500 ring-offset-2'
                    : 'border-slate-200 text-slate-600'
            )}
        >
            <Icon
                aria-hidden="true"
                className={cn('h-12 w-12 transition-colors', isSelected ? 'text-brand-600' : 'text-slate-400')}
            />
            <div className="space-y-1">
                <span
                    className={cn('block text-base transition-colors', isSelected ? 'font-semibold text-brand-700' : 'font-medium text-slate-700')}
                >
                    {option.label}
                </span>
                <p className={cn('text-sm', isSelected ? 'text-brand-600' : 'text-slate-500')}>{option.description}</p>
            </div>
        </button>
    );
}
