import Link from 'next/link';
import type { Route } from 'next';
import { Check, QrCode, Star, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SiteContainer } from '@/components/layout/site-container';

const BULLETS = [
    'QR visible y listo para escanear',
    'Diseño con logo, colores y tipografía',
    'Ideal para mesas, mostradores, recepción, caja o vidriera',
    'Más oportunidades de recibir reseñas reales de tus clientes',
] as const;

function PosterMockup() {
    return (
        <div className="relative mx-auto w-fit select-none">
            {/* Shadow layer */}
            <div className="absolute inset-0 translate-x-3 translate-y-3 rounded-2xl bg-brand-200/50 blur-sm" />

            {/* Card */}
            <div className="relative w-[220px] sm:w-[244px] rounded-2xl bg-white shadow-xl border border-slate-100 overflow-hidden flex flex-col">
                {/* Top gradient accent */}
                <div className="h-1.5 bg-gradient-to-r from-brand-600 to-brand-400" />

                {/* Brand header */}
                <div className="bg-slate-50 border-b border-slate-100 px-5 py-3 flex items-center justify-between">
                    <span className="text-[11px] font-bold tracking-[0.18em] uppercase text-brand-600">
                        Mi Rubro
                    </span>
                    <span className="text-[9px] text-slate-400">QR Reseñas</span>
                </div>

                {/* Body */}
                <div className="flex flex-col items-center gap-3 px-5 py-6 text-center">
                    <p className="text-slate-800 font-bold text-[13px] leading-snug">
                        ¿Cómo fue tu<br />experiencia hoy?
                    </p>
                    <p className="text-slate-500 text-[11px] leading-snug">
                        Escaneá el código<br />y contanos
                    </p>

                    {/* QR visual */}
                    <div className="flex items-center justify-center w-[92px] h-[92px] rounded-lg bg-slate-900 shadow-inner mt-1">
                        <QrCode className="h-16 w-16 text-white" strokeWidth={1.25} />
                    </div>

                    {/* Stars */}
                    <div className="flex gap-0.5 mt-1">
                        {Array.from({ length: 5 }).map((_, i) => (
                            <Star key={i} className="h-3.5 w-3.5 text-amber-400 fill-amber-400" />
                        ))}
                    </div>

                    <p className="text-[10px] text-slate-400 leading-snug">
                        Tu opinión nos ayuda<br />a mejorar cada día
                    </p>
                </div>

                {/* Footer */}
                <div className="bg-slate-50 border-t border-slate-100 px-4 py-2.5 text-center">
                    <p className="text-[9px] text-slate-400 font-medium tracking-wide">
                        mirubro.com · reseñas
                    </p>
                </div>
            </div>
        </div>
    );
}

export function ResenasPosterSection() {
    return (
        <section className="py-16 lg:py-24 bg-white">
            <SiteContainer>
                <div className="grid gap-12 lg:grid-cols-2 lg:gap-16 items-center">
                    {/* Left — Mockup (second on mobile, first on desktop) */}
                    <div className="flex items-center justify-center order-2 lg:order-1">
                        <PosterMockup />
                    </div>

                    {/* Right — Copy */}
                    <div className="order-1 lg:order-2 space-y-6">
                        <p className="text-sm font-semibold uppercase tracking-[0.25em] text-brand-600">
                            Carteles para tu local
                        </p>

                        <h2
                            className="font-display font-bold text-slate-900 leading-tight"
                            style={{ fontSize: 'clamp(1.75rem, 3vw, 2.5rem)' }}
                        >
                            Convertí tu QR en un cartel
                            <br className="hidden sm:block" /> listo para mostrar
                        </h2>

                        <p className="text-base text-slate-600 leading-relaxed">
                            Con QR Reseñas Pro podés crear carteles imprimibles con tu QR, tu marca y mensajes
                            personalizados para pedir reseñas en el momento justo: en la mesa, el mostrador,
                            la caja o la vidriera.
                        </p>

                        <ul className="space-y-3">
                            {BULLETS.map((bullet) => (
                                <li key={bullet} className="flex items-start gap-2.5 text-sm text-slate-700">
                                    <Check className="h-4 w-4 mt-0.5 text-brand-500 flex-shrink-0" />
                                    {bullet}
                                </li>
                            ))}
                        </ul>

                        {/* Pro badge */}
                        <div className="inline-flex items-center gap-2 rounded-full bg-brand-50 border border-brand-200/60 px-3.5 py-1.5">
                            <span className="h-2 w-2 rounded-full bg-brand-500 flex-shrink-0" />
                            <span className="text-xs font-semibold text-brand-700">
                                Incluido en QR Reseñas Pro
                            </span>
                        </div>

                        {/* CTAs */}
                        <div className="flex flex-col sm:flex-row gap-3 pt-2">
                            <Button
                                asChild
                                size="lg"
                                className="h-12 px-8 text-base font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-500/25"
                            >
                                <Link href={'#planes-resenas' as Route}>
                                    Ver QR Reseñas Pro
                                    <ArrowRight className="ml-2 h-4 w-4" />
                                </Link>
                            </Button>
                            <Button
                                asChild
                                variant="outline"
                                size="lg"
                                className="h-12 px-8 text-base border-slate-200 hover:bg-slate-50 text-slate-700 bg-transparent"
                            >
                                <Link href={'#planes-resenas' as Route}>Conocer planes</Link>
                            </Button>
                        </div>
                    </div>
                </div>
            </SiteContainer>
        </section>
    );
}
