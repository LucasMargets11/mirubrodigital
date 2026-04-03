'use client';

import { useState } from 'react';

import { getClientApiBaseUrl } from '@/lib/api-url';

const API_URL = getClientApiBaseUrl();

type ServiceOption = {
    code: string;
    label: string;
    description: string;
};

const SERVICE_OPTIONS: ServiceOption[] = [
    {
        code: 'gestion',
        label: 'Gestión Comercial',
        description: 'Ventas, stock, clientes, caja y facturación para comercios.',
    },
    {
        code: 'restaurante',
        label: 'Restaurante',
        description: 'Mesas, pedidos, cocina y delivery para gastronomía.',
    },
    {
        code: 'menu_qr',
        label: 'Menú QR',
        description: 'Carta digital con código QR para que tus clientes vean tu menú.',
    },
    {
        code: 'qr_reviews',
        label: 'QR de Reseñas',
        description: 'Un QR para que tus clientes dejen reseñas en Google fácilmente.',
    },
];

/**
 * Step 1 of the onboarding funnel: service type selection.
 *
 * This is a client component because it needs React state for the radio selection
 * and a router.push() call on submit.  The parent layout.tsx is a server component
 * that handles session validation and the onboarding/non-onboarding redirect.
 */
export default function OnboardingServicioPage() {
    const [selected, setSelected] = useState<string>('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (!selected) return;

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

            // Step 1 done → step 2: plan selection
            window.location.assign('/app/onboarding/plan');
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
                {SERVICE_OPTIONS.map((opt) => (
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
                        disabled={!selected || loading}
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
