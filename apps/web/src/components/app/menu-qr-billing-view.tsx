import Link from 'next/link';
import type { Route } from 'next';

const SERVICE_LABELS: Record<string, string> = {
    menu_qr: 'Menú QR Online',
    restaurante: 'Restaurante Inteligente',
};

const PLAN_LABELS: Record<string, string> = {
    menu_qr: 'Menú QR Online',
    plus: 'Restaurante Inteligente (Plus)',
    starter: 'Restaurante Inteligente (Starter)',
};

const STATUS_LABELS: Record<string, { label: string; className: string }> = {
    active: { label: 'Activo', className: 'bg-green-100 text-green-800' },
    inactive: { label: 'Inactivo', className: 'bg-slate-100 text-slate-600' },
    trial: { label: 'Período de prueba', className: 'bg-blue-100 text-blue-800' },
    cancelled: { label: 'Cancelado', className: 'bg-red-100 text-red-800' },
};

interface Props {
    service: string;
    plan: string;
    status: string;
    businessName: string;
}

export function MenuQrBillingView({ service, plan, status, businessName }: Props) {
    const serviceLabel = SERVICE_LABELS[service] ?? service;
    const planLabel = PLAN_LABELS[plan] ?? plan;
    const statusInfo = STATUS_LABELS[status] ?? { label: status, className: 'bg-slate-100 text-slate-600' };
    const pricingHref = `/pricing${service === 'menu_qr' ? '?service=menu_qr' : '?service=restaurante'}`;

    return (
        <section className="space-y-6">
            <header>
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-500">{serviceLabel}</p>
                <h1 className="text-3xl font-display font-bold text-slate-900">Plan y Facturación</h1>
            </header>

            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="mb-4 flex items-start justify-between">
                    <div>
                        <p className="text-xs uppercase tracking-wide text-slate-400">Negocio</p>
                        <p className="mt-0.5 text-lg font-semibold text-slate-900">{businessName}</p>
                    </div>
                    <span
                        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusInfo.className}`}
                    >
                        {statusInfo.label}
                    </span>
                </div>

                <div className="border-t border-slate-100 pt-4">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Plan actual</p>
                    <p className="mt-0.5 text-base font-semibold text-slate-800">{planLabel}</p>
                </div>

                <div className="mt-6 flex flex-wrap gap-3">
                    <a
                        href={pricingHref}
                        className="rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 transition-colors"
                    >
                        Ver planes disponibles
                    </a>
                    <a
                        href="mailto:soporte@mirubro.com"
                        className="rounded-full border border-slate-300 px-5 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
                    >
                        Contactar soporte
                    </a>
                </div>
            </div>

            {service === 'menu_qr' && (
                <div className="rounded-2xl border border-dashed border-brand-300 bg-brand-50/50 p-6">
                    <p className="text-sm font-semibold text-brand-700">Acceso incluido en tu plan</p>
                    <ul className="mt-3 space-y-2 text-sm text-slate-700">
                        <li className="flex items-center gap-2">
                            <span className="text-green-600">✓</span> Creá y editá tu menú digital
                        </li>
                        <li className="flex items-center gap-2">
                            <span className="text-green-600">✓</span> Generá tu código QR personalizado
                        </li>
                        <li className="flex items-center gap-2">
                            <span className="text-green-600">✓</span> Publicá tu menú online
                        </li>
                        <li className="flex items-center gap-2">
                            <span className="text-green-600">✓</span> Personalizá colores, logo y tipografías
                        </li>
                    </ul>
                    <p className="mt-4 text-xs text-slate-500">
                        Para acceder a mesas, pedidos, cocina y gestión de sala, conocé el plan{' '}
                        <a href="/pricing?service=restaurante" className="text-brand-600 hover:underline">
                            Restaurante Inteligente
                        </a>
                        .
                    </p>
                </div>
            )}
        </section>
    );
}
