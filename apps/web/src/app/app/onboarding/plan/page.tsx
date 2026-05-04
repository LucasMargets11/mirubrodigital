import Link from 'next/link';
import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { serverApiFetch } from '@/lib/api/server';
import { formatPrice } from '@/lib/pricing/format';

// Route constants — string variables avoid typed-routes literal checks on newly
// created pages whose route types haven't been regenerated yet by the Next.js
// compilation step.
const STEP1_ROUTE = '/app/onboarding/servicio';
const CHECKOUT_ROUTE = '/app/onboarding/checkout';

type BillingProduct = {
    code: string;
    vertical: string;
    name: string;
    description: string;
    is_active: boolean;
    order: number;
};

export function buildBundlesPath(vertical: string): string {
    return `/api/v1/billing/bundles/?vertical=${vertical}&checkout=true`;
}

export function resolveSelectedProduct(
    serviceType: string,
    products: BillingProduct[],
): BillingProduct | null {
    return products.find((product) => product.code === serviceType) ?? null;
}

function fallbackVerticalForService(serviceType: string): string {
    if (serviceType === 'gestion') return 'commercial';
    if (serviceType === 'resto') return 'restaurant';
    if (serviceType === 'menu_qr') return 'menu_qr';
    if (serviceType === 'qr_reviews') return 'qr_reviews';
    return 'commercial';
}

type OnboardingStatus = {
    step: string;
    service_type: string | null;
    email_verified: boolean;
    can_proceed: boolean;
};

type PlanBundle = {
    code: string;
    name: string;
    description: string;
    fixed_price_monthly: number | null;
    fixed_price_yearly: number | null;
    badge: string | null;
    is_default_recommended: boolean;
    is_custom: boolean;
    sort_order: number;
    cta_label: string;
};

/**
 * Step 2 of the onboarding funnel: plan selection.
 *
 * This is a server component that fetches the available modules/plans for the
 * user's selected service type, then renders plan cards linking to checkout.
 *
 * If ?plan_code is present in URL params (forwarded from /pricing → /subscribe
 * → onboarding), skip this page entirely and go straight to checkout.
 *
 * If service_type is not set yet (user navigated here directly), redirect back
 * to step 1.
 */
type Props = {
    searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export default async function OnboardingPlanPage({ searchParams }: Props) {
    const params = await searchParams;
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    // ── Plan pre-selected from URL — skip to checkout ─────────────────────
    const preselectedPlan = params.plan_code ? String(params.plan_code) : '';
    if (preselectedPlan) {
        redirect((`${CHECKOUT_ROUTE}?plan=${encodeURIComponent(preselectedPlan)}`) as never);
    }

    // Fetch the canonical service_type from the onboarding status endpoint.
    // session.current.service resolves to 'gestion' by default (build_business_context
    // fallback) even before the user selects a service during onboarding, so we
    // cannot rely on it here — it would always show commercial plans.
    let onboardingStatus: OnboardingStatus | null = null;
    try {
        onboardingStatus = await serverApiFetch<OnboardingStatus>('/api/v1/auth/onboarding/');
    } catch {
        // Non-fatal: null check below will redirect to step 1.
    }

    const serviceType = onboardingStatus?.service_type ?? '';
    if (!serviceType) {
        // service_type not set yet — user must complete step 1 first.
        redirect(STEP1_ROUTE as never);
    }

    let products: BillingProduct[] = [];
    try {
        const productData = await serverApiFetch<BillingProduct[]>('/api/v1/billing/products/');
        products = Array.isArray(productData) ? productData : [];
    } catch {
        // Non-fatal: we'll fallback to serviceType when product catalog fails.
    }

    const selectedProduct = resolveSelectedProduct(serviceType, products);
    const vertical = selectedProduct?.vertical ?? fallbackVerticalForService(serviceType);

    let bundles: PlanBundle[] = [];
    let bundlesFetchFailed = false;
    try {
        const data = await serverApiFetch<PlanBundle[]>(buildBundlesPath(vertical));
        // API already filters checkout=true, but we defensively strip any
        // is_custom or null-price bundles that might slip through.
        const all = Array.isArray(data) ? [...data].sort((a, b) => a.sort_order - b.sort_order) : [];
        bundles = all.filter((b) => !b.is_custom && b.fixed_price_monthly !== null);
    } catch {
        bundlesFetchFailed = true;
    }
    const serviceLabel = selectedProduct?.name ?? serviceType;

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
                Elegí tu plan de {serviceLabel}
            </h1>
            <p className="text-sm text-slate-500 mb-8">
                Todos los planes incluyen 14 días de prueba gratuita. Sin tarjeta de crédito requerida.
            </p>

            {bundles.length === 0 ? (
                <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center">
                    <p className="text-sm font-medium text-red-700 mb-1">
                        {bundlesFetchFailed
                            ? 'Error al cargar los planes. Verificá tu conexión.'
                            : `No hay planes disponibles para ${serviceLabel}.`}
                    </p>
                    <p className="text-xs text-red-600 mb-4">
                        {bundlesFetchFailed
                            ? 'Intentá de nuevo o contactá soporte si el problema persiste.'
                            : 'Contactá soporte para configurar los planes de tu producto.'}
                    </p>
                    <a
                        href="/app/onboarding/plan"
                        className="text-sm font-medium text-red-700 underline"
                    >
                        Reintentar
                    </a>
                </div>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {/* Onboarding context: only checkout-enabled plans are shown.
                        is_custom and null-price bundles (Empresarial / contact-only)
                        are excluded at both the API level (?checkout=true) and
                        client-side for defense-in-depth. */}
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
                                {bundle.fixed_price_monthly != null
                                    ? <>{formatPrice(bundle.fixed_price_monthly)}<span className="text-xs font-normal text-slate-400">/mes</span></>
                                    : <span className="text-slate-500 font-semibold">Hablemos</span>}
                            </p>
                            {/* All bundles rendered here have a price and are
                                checkout-enabled (is_custom=false). CTA always
                                goes to the checkout step — no /contacto links
                                in the onboarding funnel. */}
                            <Link
                                href={`${CHECKOUT_ROUTE}?plan=${bundle.code}&product=${encodeURIComponent(serviceType)}` as never}
                                className="mt-3 block w-full text-center py-2 px-4 bg-slate-900 text-white 
                                           text-xs font-medium rounded-md hover:bg-slate-800 transition-colors"
                            >
                                {bundle.cta_label || 'Elegir plan'}
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
