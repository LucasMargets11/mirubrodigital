/**
 * /subscribe — Punto de entrada público para selección de plan por usuarios no autenticados.
 *
 * Este era un formulario legacy de registro+suscripción en un solo paso que quedó
 * huérfano (importaba `@/components/ui/input` y `@/components/ui/label` que no existen).
 *
 * Flujo correcto:
 *   /pricing → selecciona plan → /subscribe?plan_code=X&billing_period=Y&vertical=Z
 *   → (este redirect) → /entrar?next=/app/onboarding?plan_code=X&billing_period=Y&vertical=Z
 *   → login/register → /app/onboarding (smart router) → checkout
 *
 * Los parámetros del plan quedan preservados en el param `next` para que después
 * del login el usuario sea enviado al onboarding con el contexto correcto.
 */
import { redirect } from 'next/navigation';

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

    const entrarParams = new URLSearchParams({ next: nextPath });
    redirect(`/entrar?${entrarParams.toString()}`);
}
