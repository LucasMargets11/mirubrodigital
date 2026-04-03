'use client';

import Link from 'next/link';
import type { Route } from 'next';
import { Check, ArrowRight, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SiteContainer } from '@/components/layout/site-container';

// ---------------------------------------------------------------------------
// QR de Reseñas is a single-tier product.
// It is available as:
//   - A standalone service (backend price: configurable)
//   - An included module in Carta Online PRO (selectable) / Premium (always)
// There is NO multi-plan comparison to show — keep it simple.
// ---------------------------------------------------------------------------

const FEATURES = [
    'QR directo a tus reseñas de Google',
    'Descarga en alta resolución (imprimible)',
    'Personalización del link de destino',
    'Analítica de escaneos y conversión',
    'Integración con tu Carta Online',
    'Compatible con cualquier dispositivo',
];

const UPSELL_FEATURES = [
    'Carta digital completa con QR incluida',
    'Propinas digitales vía Mercado Pago',
    'Analítica avanzada de engagement',
    'Dominio personalizado (Premium)',
    'Multi-sucursal (Premium)',
];

export function ResenasPricingSection() {
    return (
        <section className="py-16 lg:py-24" id="planes-resenas">
            <SiteContainer>
                <div className="space-y-10">
                    {/* Header */}
                    <div className="text-center max-w-2xl mx-auto space-y-3">
                        <p className="text-sm font-semibold uppercase tracking-[0.25em] text-brand-600">
                            Planes
                        </p>
                        <h2 className="text-3xl font-display font-bold text-slate-900">
                            Incluido en tu Carta Online
                        </h2>
                        <p className="text-lg text-slate-600">
                            El QR de Reseñas está disponible como módulo dentro de{' '}
                            <Link href={'/carta' as Route} className="text-brand-600 font-medium hover:underline">
                                Carta Online
                            </Link>{' '}
                            Pro y Premium.
                        </p>
                    </div>

                    {/* Two-column layout */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-3xl mx-auto">
                        {/* Main card - What's included */}
                        <div className="rounded-2xl border border-brand-200 bg-brand-50/30 p-6 flex flex-col">
                            <div className="mb-1">
                                <span className="inline-block bg-brand-500 text-white text-xs font-bold px-3 py-1 rounded-full">
                                    Módulo de Reseñas
                                </span>
                            </div>
                            <h3 className="text-xl font-bold text-slate-900 mt-3 mb-1">QR de Reseñas</h3>
                            <p className="text-sm text-slate-500 mb-5">
                                Incluido en Carta Online Pro (como módulo elegible) y Premium (siempre incluido).
                            </p>

                            <ul className="space-y-2.5 flex-1">
                                {FEATURES.map((feat) => (
                                    <li key={feat} className="flex items-start gap-2 text-sm text-slate-700">
                                        <Check className="h-4 w-4 mt-0.5 text-green-500 flex-shrink-0" />
                                        {feat}
                                    </li>
                                ))}
                            </ul>

                            <div className="mt-6 pt-4 border-t border-brand-100">
                                <Button asChild size="lg" className="w-full bg-brand-600 hover:bg-brand-500 text-white shadow-md">
                                    <Link href={'/pricing?service=menu_qr' as Route}>
                                        Ver planes de Carta Online
                                        <ArrowRight className="ml-2 h-4 w-4" />
                                    </Link>
                                </Button>
                            </div>
                        </div>

                        {/* Upsell card - Carta Online */}
                        <div className="rounded-2xl border border-slate-200 bg-white p-6 flex flex-col shadow-sm">
                            <div className="flex items-center gap-2 mb-3">
                                <Sparkles className="w-5 h-5 text-amber-500" />
                                <h3 className="text-lg font-bold text-slate-900">
                                    ¿Querés más que reseñas?
                                </h3>
                            </div>
                            <p className="text-sm text-slate-500 mb-5">
                                Con Carta Online tenés todo: carta digital, reseñas, propinas y analítica en un solo lugar.
                            </p>
                            <ul className="space-y-2.5 flex-1">
                                {UPSELL_FEATURES.map((feat) => (
                                    <li key={feat} className="flex items-start gap-2 text-sm text-slate-700">
                                        <Check className="h-4 w-4 mt-0.5 text-brand-500 flex-shrink-0" />
                                        {feat}
                                    </li>
                                ))}
                            </ul>
                            <div className="mt-6 pt-4 border-t border-slate-100">
                                <Button asChild size="lg" variant="secondary" className="w-full bg-slate-100 text-slate-900 hover:bg-slate-200">
                                    <Link href={'/carta' as Route}>
                                        Conocer Carta Online
                                        <ArrowRight className="ml-2 h-4 w-4" />
                                    </Link>
                                </Button>
                            </div>
                        </div>
                    </div>

                    <p className="text-xs text-center text-slate-400">
                        Las reseñas de Google son gestionadas por el propio perfil de Google Business del local.
                    </p>
                </div>
            </SiteContainer>
        </section>
    );
}
