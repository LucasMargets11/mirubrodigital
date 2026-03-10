import Link from 'next/link';
import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { serverApiFetch } from '@/lib/api/server';

// Route constants — string variables avoid typed-routes literal checks on newly
// created pages whose route types haven't been regenerated yet by the Next.js
// compilation step.
const STEP1_ROUTE = '/app/onboarding/servicio';
const CHECKOUT_ROUTE = '/app/onboarding/checkout';

type PlanBundle = {
    code: string;
    name: string;
    description: string;
    fixed_price_monthly: number | null;
    fixed_price_yearly: number | null;
    badge: string | null;
    is_default_recommended: boolean;
};

/**
 * Step 2 of the onboarding funnel: plan selection.
 *
 * This is a server component that fetches the available modules/plans for the
 * user's selected service type, then renders plan cards linking to /app/servicios
 * where the existing billing hub handles checkout creation.
 *
 * If service_type is not set yet (user navigated here directly), redirect back
 * to step 1.
 */
export default async function OnboardingPlanPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    // If service_type not yet selected, bounce back to step 1.
    const serviceType = session.current?.service ?? '';
    // Use service_type from the business (canonical) instead of the resolved active
    // service — the resolved service may default to 'gestion' even when unset.
    // The onboarding status endpoint gives us the canonical value; here we
    // use the session's current.service as proxy (it's set from service_type | default_service).
    if (!serviceType) {
        redirect(STEP1_ROUTE as never);
    }

    // Vertical map: service_type → billing vertical param
    const verticalMap: Record<string, string> = {
        gestion: 'commercial',
        restaurante: 'restaurant',
        menu_qr: 'menu_qr',
    };
    const vertical = verticalMap[serviceType] ?? 'commercial';

    let bundles: PlanBundle[] = [];
    try {
        const data = await serverApiFetch<PlanBundle[]>(
            `/api/v1/billing/bundles/?vertical=${vertical}`
        );
        bundles = Array.isArray(data) ? data : [];
    } catch {
        // Non-fatal: render with empty list and a retry hint.
    }

    const serviceLabel: Record<string, string> = {
        gestion: 'Gestión Comercial',
        restaurante: 'Restaurante',
        menu_qr: 'Menú QR',
    };

    return (
        <div className="w-full max-w-3xl">
            {/* Step indicator */}
            <div className="flex items-center gap-2 mb-8 text-xs text-slate-500">
                <span className="text-slate-400">1. Servicio</span>
                <span>→</span>
                <span className="font-semibold text-slate-900">2. Plan</span>
                <span>→</span>
                <span>3. Confirmación</span>
            </div>

            <h1 className="text-2xl font-semibold text-slate-900 mb-2">
                Elegí tu plan de {serviceLabel[serviceType] ?? serviceType}
            </h1>
            <p className="text-sm text-slate-500 mb-8">
                Todos los planes incluyen 14 días de prueba gratuita. Sin tarjeta de crédito requerida.
            </p>

            {bundles.length === 0 ? (
                <div className="rounded-lg border border-slate-200 bg-white p-6 text-center">
                    <p className="text-sm text-slate-500 mb-4">
                        No pudimos cargar los planes disponibles.
                    </p>
                    <a
                        href="/app/onboarding/plan"
                        className="text-sm text-slate-900 underline"
                    >
                        Reintentar
                    </a>
                </div>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {bundles.map((bundle) => (
                        <div
                            key={bundle.code}
                            className="flex flex-col rounded-lg border border-slate-200 bg-white p-5"
                        >
                            <div className="flex items-center justify-between mb-1">
                                <p className="text-sm font-semibold text-slate-900">{bundle.name}</p>
                                {bundle.badge ? (
                                    <span className="text-xs font-medium text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                                        {bundle.badge}
                                    </span>
                                ) : null}
                            </div>
                            <p className="text-xs text-slate-500 mb-4 flex-1">{bundle.description}</p>
                            <p className="text-lg font-bold text-slate-900 mb-1">
                                ${bundle.fixed_price_monthly != null
                                    ? (bundle.fixed_price_monthly / 100).toLocaleString('es-AR')
                                    : '—'}
                                <span className="text-xs font-normal text-slate-400">/mes</span>
                            </p>
                            {/* Navigate to the onboarding checkout page with the
                                plan pre-selected.  start-checkout is idempotent so
                                re-clicking the same plan returns the existing session. */}
                            <Link
                                href={`${CHECKOUT_ROUTE}?plan=${bundle.code}` as never}
                                className="mt-3 block w-full text-center py-2 px-4 bg-slate-900 text-white 
                                           text-xs font-medium rounded-md hover:bg-slate-800 transition-colors"
                            >
                                Elegir plan
                            </Link>
                        </div>
                    ))}
                </div>
            )}

            {/* Back link */}
            <div className="mt-8">
                <Link
                    href={STEP1_ROUTE as never}
                    className="text-xs text-slate-500 hover:text-slate-700 underline"
                >
                    ← Cambiar tipo de servicio
                </Link>
            </div>
        </div>
    );
}
