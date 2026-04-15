/**
 * /subscribe — Punto de entrada para selección de plan.
 *
 * Flujo correcto:
 *   /pricing → selecciona plan → /subscribe?plan_code=X&billing_period=Y&vertical=Z
 *
 * Dependiendo del estado de autenticación:
 *   - Sin sesión → /entrar?next=/app/onboarding?plan_code=X&billing_period=Y&vertical=Z
 *   - Sesión + business en onboarding → /app/onboarding?plan_code=X&...  (skip entrar)
 *   - Sesión + business activo → /app/servicios  (billing hub, ya tiene suscripción)
 *
 * Los parámetros del plan quedan preservados para que el onboarding
 * pueda pre-seleccionar servicio y plan sin fricción.
 */
import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

type Props = {
    searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export default async function SubscribePage({ searchParams }: Props) {
    const params = await searchParams;

    // Construir la URL de destino post-login con los parámetros del plan preservados
    const onboardingParams = new URLSearchParams();
    if (params.plan_code)      onboardingParams.set('plan_code',      String(params.plan_code));
    if (params.billing_period) onboardingParams.set('billing_period', String(params.billing_period));
    if (params.vertical)       onboardingParams.set('vertical',       String(params.vertical));
    if (params.branches)       onboardingParams.set('branches',       String(params.branches));
    if (params.add_invoicing)  onboardingParams.set('add_invoicing',  String(params.add_invoicing));
    if (params.pro_included_module) onboardingParams.set('pro_included_module', String(params.pro_included_module));
    if (params.addons)         onboardingParams.set('addons',         String(params.addons));

    const nextPath = onboardingParams.toString()
        ? `/app/onboarding?${onboardingParams.toString()}`
        : '/app/onboarding';

    // ── Shortcut para usuarios ya autenticados ────────────────────────────
    const session = await getSession();

    if (session) {
        const businessStatus = session.current?.business?.status;

        if (businessStatus && businessStatus !== 'onboarding') {
            // Business ya activo — no puede re-onboardear.
            // Enviar al billing hub donde puede gestionar su plan.
            redirect('/app/servicios' as never);
        }

        // Business en onboarding — ir directo sin pasar por /entrar.
        redirect(nextPath as never);
    }

    // ── Sin sesión — flujo estándar: login/register primero ───────────────
    const entrarParams = new URLSearchParams({ next: nextPath });
    redirect(`/entrar?${entrarParams.toString()}`);
}
