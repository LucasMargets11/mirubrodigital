import { Mail, MessageSquare } from 'lucide-react';
import { SiteContainer } from '@/components/layout/site-container';
import { CONTACT_EMAIL, CONTACT_WHATSAPP_NUMBER, CONTACT_WHATSAPP_DISPLAY } from '../_constants';

export function ContactHero() {
    return (
        <section className="bg-gradient-to-b from-brand-50/60 to-white py-20 lg:py-28">
            <SiteContainer className="text-center">
                <p className="text-sm font-semibold uppercase tracking-wider text-brand-600">
                    Hablemos
                </p>

                <h1 className="mx-auto mt-3 max-w-3xl font-display text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl lg:text-6xl">
                    Contacto
                </h1>

                <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-slate-600 sm:text-xl">
                    Si querés conocer más sobre Mi&nbsp;Rubro, solicitar
                    información comercial o resolver una consulta general,
                    escribinos y te ayudamos.
                </p>

                <p className="mx-auto mt-3 max-w-xl text-base leading-relaxed text-slate-500">
                    También podés contactarte si querés recibir una demo,
                    consultar sobre nuestras soluciones o explorar cuál se
                    adapta mejor a tu negocio.
                </p>

                <div className="mt-8 flex flex-col items-center justify-center gap-4 sm:flex-row">
                    <a
                        href={`mailto:${CONTACT_EMAIL}`}
                        className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-500"
                    >
                        <Mail className="h-4 w-4" />
                        Escribinos por email
                    </a>
                    <a
                        href="#formulario"
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-6 py-3 text-sm font-semibold text-slate-700 transition hover:border-brand-300 hover:text-brand-600"
                    >
                        <MessageSquare className="h-4 w-4" />
                        Contactanos por WhatsApp
                    </a>
                </div>
            </SiteContainer>
        </section>
    );
}
