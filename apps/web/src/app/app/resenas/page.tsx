import { redirect } from 'next/navigation';
import Link from 'next/link';
import type { Route } from 'next';
import { Check, ArrowRight } from 'lucide-react';

import { getSession } from '@/lib/auth';
import { Button } from '@/components/ui/button';
import {
    PRODUCT,
    PRODUCT_BENEFITS,
    CTA_PRIMARY,
    SMART_FILTER,
    REVIEW_PRICING_CARDS,
} from '@/features/reviews/product';
import { ReviewsDashboardClient } from './dashboard-client';

export default async function ResenasPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    return (
        <>
            {/* ── Header ───────────────────────────────────────── */}
            <header className="space-y-1">
                <h1 className="text-3xl font-display font-bold text-slate-900">
                    {PRODUCT.name}
                </h1>
                <p className="text-sm text-slate-500">
                    {PRODUCT.tagline}{' · '}
                    <span className="font-medium text-slate-700">{session.current.business.name}</span>
                </p>
            </header>

            {/* ── Resultados tangibles ─────────────────────────── */}
            <div className="rounded-2xl border border-brand-100 bg-brand-50/40 p-5 space-y-3">
                <h2 className="text-sm font-semibold text-slate-800">¿Qué lográs con QR de Reseñas?</h2>
                <p className="text-sm text-slate-600">{PRODUCT.description}</p>
                <ul className="space-y-1.5 text-sm text-slate-700">
                    {PRODUCT_BENEFITS.map((b) => (
                        <li key={b} className="flex items-center gap-2">
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                            {b}
                        </li>
                    ))}
                </ul>
            </div>

            {/* ── CTA dominante ─────────────────────────────────── */}
            <div className="flex flex-col sm:flex-row gap-3">
                <Link
                    href={CTA_PRIMARY.href as Route}
                    className="inline-flex items-center justify-center gap-2 rounded-full bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-md hover:bg-brand-700 transition-colors"
                >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z" /></svg>
                    {CTA_PRIMARY.label}
                </Link>
                <Link
                    href={'/app/resenas/feedback' as Route}
                    className="inline-flex items-center justify-center gap-2 rounded-full border border-slate-300 px-6 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
                >
                    Ver feedback
                </Link>
                <Link
                    href={'/app/resenas/configuracion' as Route}
                    className="inline-flex items-center justify-center gap-2 rounded-full border border-slate-300 px-6 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
                >
                    Configurar
                </Link>
            </div>

            {/* ── Smart filter — diferenciador ─────────────────── */}
            <div className="rounded-2xl border border-indigo-100 bg-indigo-50/30 p-5 space-y-3">
                <h2 className="text-base font-bold text-slate-900">{SMART_FILTER.headline}</h2>
                <p className="text-sm text-slate-600">{SMART_FILTER.description}</p>
                <div className="grid gap-2 sm:grid-cols-2">
                    {SMART_FILTER.bullets.map((b) => (
                        <div key={b.label} className="flex items-center gap-3 rounded-lg bg-white p-3 border border-indigo-100">
                            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-700">
                                {b.label.startsWith('≥') ? '★' : '☆'}
                            </span>
                            <div className="text-sm">
                                <p className="font-semibold text-slate-700">{b.label}</p>
                                <p className="text-slate-500 text-xs">{b.result}</p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* ── Planes ───────────────────────────────────────── */}
            <div className="space-y-4">
                <h2 className="text-lg font-display font-bold text-slate-900">Elegí tu plan</h2>
                <div className="grid gap-6 sm:grid-cols-2">
                    {REVIEW_PRICING_CARDS.map((plan) => (
                        <div
                            key={plan.name}
                            className={`rounded-2xl border p-6 flex flex-col ${
                                plan.featured
                                    ? 'border-brand-200 bg-brand-50/30 shadow-lg ring-1 ring-brand-100'
                                    : 'border-slate-200 bg-white shadow-sm'
                            }`}
                        >
                            <div className="space-y-1">
                                <h3 className="text-lg font-semibold text-slate-900">{plan.name}</h3>
                                <p className="text-sm text-slate-500">{plan.tagline}</p>
                            </div>

                            <div className="mt-4">
                                <span className="text-3xl font-bold text-slate-900">{plan.price}</span>
                                {plan.period && (
                                    <span className="text-sm text-slate-500 ml-1">{plan.period}</span>
                                )}
                            </div>

                            <ul className="mt-6 space-y-2.5 flex-1">
                                {plan.highlights.map((h) => (
                                    <li key={h} className="flex items-start gap-2 text-sm text-slate-600">
                                        <Check className="h-4 w-4 mt-0.5 text-brand-500 flex-shrink-0" />
                                        {h}
                                    </li>
                                ))}
                            </ul>

                            <div className="mt-6">
                                <Button
                                    asChild
                                    size="lg"
                                    className={`w-full ${
                                        plan.featured
                                            ? 'bg-brand-600 hover:bg-brand-500 text-white'
                                            : ''
                                    }`}
                                    variant={plan.featured ? 'default' : 'outline'}
                                >
                                    <Link href={plan.ctaHref as Route}>
                                        {plan.ctaLabel}
                                        <ArrowRight className="ml-2 h-4 w-4" />
                                    </Link>
                                </Button>
                            </div>
                        </div>
                    ))}
                </div>
                <p className="text-xs text-slate-400 text-center">
                    Los planes se gestionan desde tu cuenta. No se requiere tarjeta para explorar.
                </p>
            </div>

            {/* ── Analytics dashboard + channel status ─────────── */}
            <ReviewsDashboardClient />
        </>
    );
}
