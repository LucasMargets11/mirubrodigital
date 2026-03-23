import type { Metadata } from 'next';
import { SiteContainer } from '@/components/layout/site-container';
import { ContactHero } from './_components/ContactHero';
import { ContactChannels } from './_components/ContactChannels';
import { ContactForm } from './_components/ContactForm';
import { ContactTopics } from './_components/ContactTopics';
import { ContactSupportRedirect } from './_components/ContactSupportRedirect';
import { ContactHelpTips } from './_components/ContactHelpTips';
import { ContactCTA } from './_components/ContactCTA';

const SITE_URL = 'https://www.mirubro.com';

export const metadata: Metadata = {
    title: 'Contacto | Mi Rubro',
    description:
        'Contactate con Mi Rubro para solicitar información, conocer nuestras soluciones o hacer una consulta general sobre la plataforma.',
    alternates: { canonical: `${SITE_URL}/contacto` },
    openGraph: {
        title: 'Contacto | Mi Rubro',
        description:
            'Contactate con Mi Rubro para solicitar información, conocer nuestras soluciones o hacer una consulta general sobre la plataforma.',
        url: `${SITE_URL}/contacto`,
        siteName: 'Mirubro',
        type: 'website',
        locale: 'es_AR',
    },
    twitter: {
        card: 'summary',
        title: 'Contacto | Mi Rubro',
        description:
            'Contactate con Mi Rubro para solicitar información, conocer nuestras soluciones o hacer una consulta general sobre la plataforma.',
    },
};

export default function ContactoPage() {
    return (
        <>
            <ContactHero />

            {/* ── Cuerpo: dos columnas en desktop ── */}
            <section className="py-20 lg:py-28">
                <SiteContainer>
                    <div className="mx-auto flex max-w-6xl flex-col gap-16 lg:flex-row lg:gap-12">
                        {/* Columna izquierda */}
                        <div className="flex w-full flex-col gap-10 lg:w-5/12">
                            <ContactChannels />
                            <ContactTopics />
                            <ContactSupportRedirect />
                            <ContactHelpTips />
                        </div>

                        {/* Columna derecha: formulario */}
                        <div className="w-full lg:w-7/12" id="formulario">
                            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
                                <h2 className="font-display text-xl font-semibold text-slate-900 sm:text-2xl">
                                    Enviános tu consulta
                                </h2>
                                <p className="mt-2 text-sm leading-relaxed text-slate-500">
                                    Completá tus datos y contanos qué necesitás.
                                    Esto nos ayuda a orientarte mejor y
                                    responderte de forma más clara.
                                </p>
                                <div className="mt-6">
                                    <ContactForm />
                                </div>
                            </div>
                        </div>
                    </div>
                </SiteContainer>
            </section>

            <ContactCTA />
        </>
    );
}
