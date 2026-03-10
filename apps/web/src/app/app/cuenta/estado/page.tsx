import Link from 'next/link';
import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

/**
 * Account/business state screen — Wave 5.
 *
 * Shown when the user's business has no active subscription and the app layout
 * has routed them here based on their `business.status`.
 *
 * URL params:
 *   ?status=suspended  — business manually suspended (admin action or billing)
 *   ?status=canceled   — subscription canceled; no further access
 *   ?status=past_due   — renewal failed and grace period has expired
 *
 * This page is listed in the layout's billingBypassPaths so it is always
 * reachable regardless of enforcement state.
 *
 * Design: minimal, localized, actionable. No sidebar dependency.
 */

type StatusParam = 'suspended' | 'canceled' | 'past_due';

type StateConfig = {
    emoji: string;
    title: string;
    description: string;
    cta: { label: string; href: string } | null;
    supportHint: string;
};

const STATE_CONFIG: Record<StatusParam, StateConfig> = {
    past_due: {
        emoji: '⚠️',
        title: 'Tu período de gracia venció',
        description:
            'Hubo un problema con el cobro de tu suscripción y el período de gracia expiró. ' +
            'Tu acceso está suspendido hasta que regularices el pago.',
        cta: { label: 'Regularizar suscripción', href: '/app/servicios' },
        supportHint: 'Si creés que esto es un error, contactá a soporte.',
    },
    suspended: {
        emoji: '🔒',
        title: 'Tu cuenta está suspendida',
        description:
            'Tu cuenta fue suspendida. Esto puede deberse a falta de pago o a una ' +
            'acción administrativa. Para reactivarla, contactá al equipo de soporte.',
        cta: null,
        supportHint: 'Contactá a soporte para resolver el problema.',
    },
    canceled: {
        emoji: '❌',
        title: 'Tu suscripción fue cancelada',
        description:
            'Tu suscripción a Mi Rubro fue cancelada. Ya no tenés acceso a las ' +
            'funcionalidades del plan. Podés volver a suscribirte cuando quieras.',
        cta: { label: 'Ver planes disponibles', href: '/app/onboarding/plan' },
        supportHint: 'Si cancelaste por error, contactá a soporte lo antes posible.',
    },
};

const FALLBACK_CONFIG: StateConfig = {
    emoji: '⚠️',
    title: 'Acceso restringido',
    description: 'Tu cuenta no tiene acceso activo en este momento.',
    cta: { label: 'Ver planes', href: '/app/planes' },
    supportHint: 'Contactá a soporte si necesitás ayuda.',
};

export default async function CuentaEstadoPage({
    searchParams,
}: {
    searchParams: Promise<{ status?: string }>;
}) {
    const session = await getSession();
    if (!session) {
        redirect('/entrar');
    }

    const { status } = await searchParams;
    const config =
        status && status in STATE_CONFIG
            ? STATE_CONFIG[status as StatusParam]
            : FALLBACK_CONFIG;

    return (
        <section className="mx-auto max-w-lg space-y-6 rounded-2xl border border-slate-200 bg-white p-8 mt-12">
            <header className="text-center space-y-3">
                <div className="text-5xl select-none">{config.emoji}</div>
                <h1 className="text-2xl font-semibold text-slate-900">{config.title}</h1>
                <p className="text-sm text-slate-500 leading-relaxed">{config.description}</p>
            </header>

            {config.cta && (
                <div className="flex justify-center">
                    <Link
                        href={config.cta.href as never}
                        className="rounded-full bg-slate-900 px-6 py-3 text-sm font-semibold text-white hover:bg-slate-800 transition-colors"
                    >
                        {config.cta.label}
                    </Link>
                </div>
            )}

            <p className="text-center text-xs text-slate-400">{config.supportHint}</p>

            <hr className="border-slate-100" />

            <div className="flex justify-center gap-6 text-xs text-slate-400">
                <Link href={'/app/settings' as never} className="hover:text-slate-600 transition-colors">
                    Configuración
                </Link>
                <a
                    href="mailto:soporte@mirubro.com"
                    className="hover:text-slate-600 transition-colors"
                >
                    Soporte
                </a>
            </div>
        </section>
    );
}
