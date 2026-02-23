'use client';

import { useState } from 'react';
import { Check, Sparkles } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { CommercialSubscription } from '@/types/billing';

interface PlanConfig {
    code: string;
    name: string;
    price_monthly: number;
    price_yearly: number;
    description: string;
    features: string[];
    branches_included: number;
    branches_extras_allowed: boolean;
    branches_max: number | null;
    seats_included: number;
    highlighted?: boolean;
}

const PLANS: PlanConfig[] = [
    {
        code: 'start',
        name: 'START',
        price_monthly: 9900,
        price_yearly: 95000,
        description: 'Para emprendimientos que comienzan',
        features: [
            '1 sucursal',
            '2 usuarios',
            '5 módulos operativos',
            'Soporte por email',
        ],
        branches_included: 1,
        branches_extras_allowed: false,
        branches_max: 1,
        seats_included: 2,
    },
    {
        code: 'pro',
        name: 'PRO',
        price_monthly: 29900,
        price_yearly: 287000,
        description: 'Para negocios en crecimiento',
        features: [
            'Hasta 3 sucursales',
            '10 usuarios',
            '15 módulos incluyendo Tesorería',
            'CRM incluido',
            'Soporte prioritario',
        ],
        branches_included: 1,
        branches_extras_allowed: true,
        branches_max: 3,
        seats_included: 10,
        highlighted: true,
    },
    {
        code: 'business',
        name: 'BUSINESS',
        price_monthly: 49900,
        price_yearly: 479000,
        description: 'Para empresas establecidas',
        features: [
            'Sucursales ilimitadas',
            '20 usuarios base',
            '19 módulos completos',
            'CRM + Facturación incluidos',
            'Soporte VIP 24/7',
        ],
        branches_included: 5,
        branches_extras_allowed: true,
        branches_max: null,
        seats_included: 20,
    },
    {
        code: 'enterprise',
        name: 'ENTERPRISE',
        price_monthly: 0,
        price_yearly: 0,
        description: 'Soluciones personalizadas',
        features: [
            'Todo ilimitado',
            'Soluciones a medida',
            'Integraciones custom',
            'Account manager dedicado',
            'SLA personalizado',
        ],
        branches_included: 999,
        branches_extras_allowed: false,
        branches_max: null,
        seats_included: 999,
    },
];

interface PlanComparisonProps {
    currentSubscription: CommercialSubscription;
    onSelectPlan: (planCode: string) => void;
}

function formatPrice(cents: number): string {
    return `$${(cents / 100).toFixed(0)}`;
}

export function PlanComparison({ currentSubscription, onSelectPlan }: PlanComparisonProps) {
    const [billingCycle, setBillingCycle] = useState<'monthly' | 'yearly'>(
        currentSubscription.billing_cycle || 'monthly'
    );

    const currentPlanCode = currentSubscription.current_plan.code;

    return (
        <div className="space-y-6">
            {/* Billing Cycle Toggle */}
            <div className="flex items-center justify-center gap-3">
                <span className={`text-sm font-medium ${billingCycle === 'monthly' ? 'text-slate-900' : 'text-slate-500'}`}>
                    Mensual
                </span>
                <button
                    onClick={() => setBillingCycle(billingCycle === 'monthly' ? 'yearly' : 'monthly')}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${
                        billingCycle === 'yearly' ? 'bg-slate-900' : 'bg-slate-300'
                    }`}
                >
                    <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${
                            billingCycle === 'yearly' ? 'translate-x-6' : 'translate-x-1'
                        }`}
                    />
                </button>
                <span className={`text-sm font-medium ${billingCycle === 'yearly' ? 'text-slate-900' : 'text-slate-500'}`}>
                    Anual
                </span>
                {billingCycle === 'yearly' && (
                    <Badge variant="secondary" className="ml-2 bg-green-100 text-green-800">
                        Ahorrá ~20%
                    </Badge>
                )}
            </div>

            {/* Plans Grid */}
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
                {PLANS.map((plan) => {
                    const isCurrent = plan.code === currentPlanCode;
                    const price = billingCycle === 'monthly' ? plan.price_monthly : plan.price_yearly;
                    const pricePerMonth = billingCycle === 'yearly' ? price / 12 : price;
                    const isEnterprise = plan.code === 'enterprise';

                    return (
                        <article
                            key={plan.code}
                            className={`relative flex flex-col rounded-2xl border p-6 shadow-sm transition hover:shadow-md ${
                                plan.highlighted
                                    ? 'border-slate-900 bg-slate-50'
                                    : isCurrent
                                        ? 'border-blue-500 bg-blue-50'
                                        : 'border-slate-200 bg-white'
                            }`}
                        >
                            {/* Badges */}
                            <div className="mb-3 flex items-center gap-2">
                                {isCurrent && (
                                    <Badge className="bg-blue-600">Plan Actual</Badge>
                                )}
                                {plan.highlighted && !isCurrent && (
                                    <Badge className="bg-slate-900">Recomendado</Badge>
                                )}
                            </div>

                            {/* Plan Name */}
                            <h3 className="text-2xl font-bold text-slate-900">{plan.name}</h3>
                            <p className="mt-2 text-sm text-slate-600">{plan.description}</p>

                            {/* Pricing */}
                            <div className="mt-4">
                                {isEnterprise ? (
                                    <div className="text-2xl font-bold text-slate-900">A medida</div>
                                ) : (
                                    <>
                                        <div className="text-3xl font-bold text-slate-900">
                                            {formatPrice(pricePerMonth)}
                                        </div>
                                        <div className="text-sm text-slate-500">
                                            /mes {billingCycle === 'yearly' && '(facturado anualmente)'}
                                        </div>
                                    </>
                                )}
                            </div>

                            {/* Features */}
                            <ul className="mt-6 flex-1 space-y-3">
                                {plan.features.map((feature, index) => (
                                    <li key={index} className="flex items-start gap-2 text-sm">
                                        <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-600" />
                                        <span className="text-slate-700">{feature}</span>
                                    </li>
                                ))}
                            </ul>

                            {/* Action Button */}
                            <div className="mt-6">
                                {isCurrent ? (
                                    <Button disabled className="w-full" variant="outline">
                                        Plan Actual
                                    </Button>
                                ) : isEnterprise ? (
                                    <Button
                                        className="w-full"
                                        variant="outline"
                                        onClick={() => {
                                            window.open('mailto:success@mirubro.com?subject=Consulta Enterprise Plan', '_blank');
                                        }}
                                    >
                                        Contactar
                                    </Button>
                                ) : (
                                    <Button
                                        className="w-full gap-2"
                                        onClick={() => onSelectPlan(plan.code)}
                                        variant={plan.highlighted ? 'default' : 'outline'}
                                    >
                                        <Sparkles className="h-4 w-4" />
                                        Seleccionar
                                    </Button>
                                )}
                            </div>
                        </article>
                    );
                })}
            </div>

            {/* Additional Info */}
            <div className="rounded-lg bg-slate-50 border border-slate-200 p-4">
                <p className="text-sm text-slate-600">
                    <strong>Nota:</strong> Los upgrades son efectivos de inmediato. Los downgrades se programan para el próximo ciclo de facturación.
                    Sucursales y usuarios extras se pueden agregar en cualquier momento.
                </p>
            </div>
        </div>
    );
}
