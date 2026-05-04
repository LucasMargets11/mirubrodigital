'use client';

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';

import { getClientApiBaseUrl } from '@/lib/api-url';
import { getBillingProducts } from '@/features/billing/api';
import type { BillingProduct } from '@/features/billing/types';

const API_URL = getClientApiBaseUrl();

type ServiceOption = {
    code: string;
    vertical: string;
    label: string;
    description: string;
};

const FALLBACK_SERVICE_OPTIONS: ServiceOption[] = [
    {
        code: 'gestion',
        vertical: 'commercial',
        label: 'Gestión Comercial',
        description: 'Ventas, stock, clientes, caja y facturación para comercios.',
    },
    {
        code: 'menu_qr',
        vertical: 'menu_qr',
        label: 'Menú QR',
        description: 'Carta digital con código QR para que tus clientes vean tu menú.',
    },
    {
        code: 'qr_reviews',
        vertical: 'qr_reviews',
        label: 'QR de Reseñas',
        description: 'Más reseñas positivas en Google y mejor reputación para tu negocio.',
    },
];

function mapProductsToServiceOptions(products: BillingProduct[]): ServiceOption[] {
    return products
        .filter((product) => product.is_active)
        .sort((a, b) => a.order - b.order)
        .map((product) => ({
            code: product.code,
            vertical: product.vertical,
            label: product.name,
            description: product.description,
        }));
}

/**
 * Step 1 of the onboarding funnel: service type selection.
 *
 * Reads ?vertical from URL (forwarded from /subscribe → /app/onboarding) to
 * pre-select the matching service, reducing friction.  After selection,
 * forwards plan_code and billing_period to the plan step.
 */
export default function OnboardingServicioPage() {
    const searchParams = useSearchParams();
    const verticalHint = searchParams.get('vertical') ?? '';
    const planCode     = searchParams.get('plan_code') ?? '';
    const billingPeriod = searchParams.get('billing_period') ?? '';

    const [serviceOptions, setServiceOptions] = useState<ServiceOption[]>([]);
    const [productsLoading, setProductsLoading] = useState(true);
    const [selected, setSelected] = useState<string>('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let alive = true;

        async function loadProducts() {
            try {
                const products = await getBillingProducts();
                if (!alive) return;
                const mapped = mapProductsToServiceOptions(products);
                setServiceOptions(mapped.length > 0 ? mapped : FALLBACK_SERVICE_OPTIONS);
            } catch {
                if (!alive) return;
                setServiceOptions(FALLBACK_SERVICE_OPTIONS);
            } finally {
                if (alive) setProductsLoading(false);
            }
        }

        loadProducts();
        return () => {
            alive = false;
        };
    }, []);

    const effectiveOptions = useMemo(
        () => (serviceOptions.length > 0 ? serviceOptions : FALLBACK_SERVICE_OPTIONS),
        [serviceOptions],
    );

    useEffect(() => {
        if (effectiveOptions.length === 0) return;
        if (selected && effectiveOptions.some((o) => o.code === selected)) return;

        const hinted = effectiveOptions.find(
            (o) => o.code === verticalHint || o.vertical === verticalHint,
        );
        setSelected(hinted?.code ?? effectiveOptions[0].code);
    }, [effectiveOptions, verticalHint, selected]);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (!selected || productsLoading) return;

        setLoading(true);
        setError(null);

        try {
            const response = await fetch(`${API_URL}/api/v1/auth/onboarding/set-service/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ service_type: selected }),
            });

            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                // 409: business already left onboarding → skip ahead to /app
                if (response.status === 409) {
                    window.location.assign('/app');
                    return;
                }
                setError(payload?.detail ?? 'No pudimos guardar tu selección. Intentalo de nuevo.');
                return;
            }

            // Step 1 done → step 2: plan selection.
            // Forward plan_code / billing_period so the plan page can skip to checkout.
            const fwd = new URLSearchParams();
            if (planCode) fwd.set('plan_code', planCode);
            if (billingPeriod) fwd.set('billing_period', billingPeriod);
            const qs = fwd.toString();
            window.location.assign(`/app/onboarding/plan${qs ? `?${qs}` : ''}`);
        } catch {
            setError('Error de red. Verificá tu conexión e intentalo de nuevo.');
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="w-full max-w-2xl">
            {/* Step indicator */}
            <div className="flex items-center gap-2 mb-8 text-xs text-slate-500">
                <span className="font-semibold text-slate-900">1. Servicio</span>
                <span>→</span>
                <span>2. Plan</span>
                <span>→</span>
                <span>3. Confirmación</span>
            </div>

            <h1 className="text-2xl font-semibold text-slate-900 mb-2">
                ¿Qué tipo de negocio tenés?
            </h1>
            <p className="text-sm text-slate-500 mb-8">
                Elegí el servicio que mejor se adapte a tu actividad. Podrás cambiarlo después.
            </p>

            <form onSubmit={handleSubmit} className="space-y-3">
                {effectiveOptions.map((opt) => (
                    <label
                        key={opt.code}
                        className={`flex items-start gap-4 p-4 rounded-lg border cursor-pointer transition-colors ${
                            selected === opt.code
                                ? 'border-slate-900 bg-slate-50'
                                : 'border-slate-200 bg-white hover:border-slate-300'
                        }`}
                    >
                        <input
                            type="radio"
                            name="service_type"
                            value={opt.code}
                            checked={selected === opt.code}
                            onChange={() => setSelected(opt.code)}
                            className="mt-0.5 accent-slate-900"
                        />
                        <div>
                            <p className="text-sm font-medium text-slate-900">{opt.label}</p>
                            <p className="text-xs text-slate-500 mt-0.5">{opt.description}</p>
                        </div>
                    </label>
                ))}

                {error && (
                    <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
                        {error}
                    </p>
                )}

                <div className="pt-4">
                    <button
                        type="submit"
                        disabled={!selected || loading || productsLoading}
                        className="w-full py-2.5 px-4 bg-slate-900 text-white text-sm font-medium rounded-lg 
                                   hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed 
                                   transition-colors"
                    >
                        {loading ? 'Guardando...' : 'Continuar'}
                    </button>
                </div>
            </form>
        </div>
    );
}
