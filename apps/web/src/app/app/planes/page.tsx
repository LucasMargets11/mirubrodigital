import { redirect } from 'next/navigation';
import Link from 'next/link';

import { getSession } from '@/lib/auth';

const SERVICE_LABELS: Record<string, string> = {
    menu_qr: 'Menú QR Online',
    menu_qr_visual: 'Menú QR Visual',
    menu_qr_marca: 'Menú QR Marca',
    restaurante: 'Restaurante Inteligente',
    gestion: 'Gestión Comercial',
};

const PLAN_LABELS: Record<string, string> = {
    menu_qr: 'Básico',
    menu_qr_visual: 'Visual',
    menu_qr_marca: 'Marca',
    restaurante: 'Restaurante',
    plus: 'Plus',
    starter: 'Starter',
    start: 'Start',
    pro: 'Pro',
    business: 'Business',
    enterprise: 'Enterprise',
};

const SERVICE_PRICING_HREF: Record<string, string> = {
    menu_qr: '/pricing?service=menu_qr',
    restaurante: '/pricing?service=restaurante',
    gestion: '/pricing',
};

export default async function PlansPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    // Gestion users have their full billing hub at /app/servicios
    const service = session.current?.service ?? 'gestion';
    if (service === 'gestion') {
        redirect('/app/servicios');
    }

    const plan = session.subscription?.plan ?? '';
    const status = session.subscription?.status ?? '';
    // For QR tiers, derive service label from the plan code so Visual/Marca show their own name
    const serviceLabel = SERVICE_LABELS[plan] ?? SERVICE_LABELS[service] ?? service;
    const planLabel = PLAN_LABELS[plan] ?? plan;
    const pricingHref = SERVICE_PRICING_HREF[service] ?? '/pricing';
    const isActive = status === 'active' || status === 'trial';

    return (
        <section className="mx-auto max-w-2xl space-y-6 rounded-2xl border border-slate-200 bg-white p-8">
            <header className="text-center">
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-500">{serviceLabel}</p>
                <h1 className="mt-1 text-3xl font-display font-bold text-slate-900">Tu plan</h1>
            </header>

            <div className="rounded-xl border border-slate-100 bg-slate-50 p-4 text-center">
                <p className="text-xs uppercase tracking-wide text-slate-400">Plan actual</p>
                <p className="mt-0.5 text-lg font-semibold text-slate-800 capitalize">{planLabel || serviceLabel}</p>
                {status && (
                    <span
                        className={`mt-2 inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            isActive ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-600'
                        }`}
                    >
                        {status === 'active' ? 'Activo' : status === 'trial' ? 'Período de prueba' : status}
                    </span>
                )}
            </div>

            <div className="flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
                <Link
                    href={pricingHref}
                    className="rounded-full bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 transition-colors"
                >
                    Ver planes disponibles
                </Link>
                <Link
                    href="/app/servicios"
                    className="rounded-full border border-slate-300 px-6 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
                >
                    Facturación
                </Link>
            </div>
        </section>
    );
}
