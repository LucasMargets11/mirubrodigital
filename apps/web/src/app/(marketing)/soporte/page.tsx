import type { Metadata } from 'next';
import Link from 'next/link';
import {
    Mail,
    MessageSquare,
    Clock,
    ListChecks,
    ArrowRight,
} from 'lucide-react';
import { SiteContainer } from '@/components/layout/site-container';
import { SUPPORT_EMAIL, USEFUL_LINKS } from './_constants';
import { SupportChannels } from './_components/SupportChannels';
import { SupportTopics } from './_components/SupportTopics';
import { SupportForm } from './_components/SupportForm';

const SITE_URL = 'https://www.mirubro.com';

export const metadata: Metadata = {
    title: 'Soporte | Mi Rubro',
    description:
        'Contactá al equipo de soporte de Mi Rubro. Enviá tu consulta por email o WhatsApp y recibí ayuda con tu cuenta, configuración o servicios.',
    alternates: { canonical: `${SITE_URL}/soporte` },
    openGraph: {
        title: 'Soporte | Mi Rubro',
        description:
            'Contactá al equipo de soporte de Mi Rubro. Enviá tu consulta por email o WhatsApp y recibí ayuda con tu cuenta, configuración o servicios.',
        url: `${SITE_URL}/soporte`,
        siteName: 'Mirubro',
        type: 'website',
        locale: 'es_AR',
    },
    twitter: {
        card: 'summary',
        title: 'Soporte | Mi Rubro',
        description:
            'Contactá al equipo de soporte de Mi Rubro. Enviá tu consulta por email o WhatsApp y recibí ayuda con tu cuenta, configuración o servicios.',
    },
};

/* ─────────────────────────────────────────────
   Page
   ───────────────────────────────────────────── */

export default function SoportePage() {
    return (
        <>
            {/* ── Hero ── */}
            <section className="bg-slate-50 border-b border-slate-200">
                <SiteContainer className="py-16 lg:py-20">
                    <div className="mx-auto max-w-2xl text-center">
                        <h1 className="font-display text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
                            Soporte de Mi Rubro
                        </h1>
                        <p className="mt-4 text-base leading-relaxed text-slate-600 sm:text-lg">
                            Te ayudamos con consultas sobre tu cuenta, configuración, uso de
                            la plataforma e inconvenientes técnicos.
                        </p>

                        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
                            <a
                                href={`mailto:${SUPPORT_EMAIL}`}
                                className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-brand-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
                            >
                                <Mail className="h-4 w-4" />
                                Escribinos por email
                            </a>
                            <a
                                href="#formulario"
                                className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-6 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition-all hover:border-brand-300 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
                            >
                                <MessageSquare className="h-4 w-4" />
                                Enviar consulta por WhatsApp
                            </a>
                        </div>
                    </div>
                </SiteContainer>
            </section>

            {/* ── Main content: 2 columns on lg ── */}
            <SiteContainer className="py-16 lg:py-20">
                <div className="mx-auto flex max-w-5xl flex-col items-center gap-16 lg:flex-row lg:items-start lg:gap-12">
                    {/* ── Left column: info blocks ── */}
                    <div className="w-full max-w-md space-y-14">
                        <SupportChannels />

                        <SupportTopics />

                        {/* Tiempos de respuesta */}
                        <section>
                            <div className="flex items-center gap-2">
                                <Clock className="h-5 w-5 text-brand-500" />
                                <h2 className="font-display text-xl font-semibold text-slate-900 sm:text-2xl">
                                    Tiempos de respuesta
                                </h2>
                            </div>
                            <p className="mt-4 text-base leading-relaxed text-slate-600">
                                Respondemos las consultas entre 24 y 48 hs hábiles desde su
                                recepción.
                            </p>
                            <p className="mt-2 text-sm text-slate-500">
                                El tiempo puede variar levemente según el volumen de consultas
                                o la complejidad del caso.
                            </p>
                        </section>

                        {/* Antes de escribirnos */}
                        <section>
                            <div className="flex items-center gap-2">
                                <ListChecks className="h-5 w-5 text-brand-500" />
                                <h2 className="font-display text-xl font-semibold text-slate-900 sm:text-2xl">
                                    Antes de escribirnos
                                </h2>
                            </div>
                            <p className="mt-4 text-base leading-relaxed text-slate-600">
                                Para agilizar la respuesta, te recomendamos incluir la mayor
                                cantidad de información posible sobre tu consulta.
                            </p>
                            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
                                <li>Nombre del comercio o local</li>
                                <li>Email asociado a tu cuenta</li>
                                <li>Producto o módulo por el que consultás</li>
                                <li>Detalle claro del problema</li>
                                <li>Capturas o contexto adicional, si aplica</li>
                            </ul>
                        </section>
                    </div>

                    {/* ── Right column: form ── */}
                    <div className="w-full max-w-lg" id="formulario">
                        <div className="scroll-mt-24 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
                            <h2 className="font-display text-xl font-semibold text-slate-900 sm:text-2xl">
                                Enviá tu consulta
                            </h2>
                            <p className="mt-2 text-sm leading-relaxed text-slate-500">
                                Completá estos datos para que podamos ayudarte más rápido. Tu
                                consulta se enviará por WhatsApp de forma provisional.
                            </p>

                            <div className="mt-6">
                                <SupportForm />
                            </div>
                        </div>
                    </div>
                </div>
            </SiteContainer>

            {/* ── Recursos útiles ── */}
            <section className="border-t border-slate-200 bg-slate-50">
                <SiteContainer className="py-12 lg:py-16">
                    <h2 className="text-center font-display text-xl font-semibold text-slate-900 sm:text-2xl">
                        Recursos útiles
                    </h2>
                    <div className="mx-auto mt-8 grid max-w-2xl gap-3 sm:grid-cols-2">
                        {USEFUL_LINKS.map((link) => (
                            <Link
                                key={link.href}
                                href={link.href as never}
                                className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-5 py-3.5 text-sm font-medium text-slate-700 shadow-sm transition-all hover:border-brand-200 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
                            >
                                {link.label}
                                <ArrowRight className="h-4 w-4 text-slate-400" />
                            </Link>
                        ))}
                    </div>
                </SiteContainer>
            </section>
        </>
    );
}
