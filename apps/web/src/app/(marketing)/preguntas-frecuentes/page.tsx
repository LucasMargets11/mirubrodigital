import type { Metadata } from 'next';
import { SiteContainer } from '@/components/layout/site-container';
import { FAQ_DATA } from './_data';
import { FAQSearch } from './_components/FAQSearch';
import { FAQCTA } from './_components/FAQCTA';

const SITE_URL = 'https://www.mirubro.com';

export const metadata: Metadata = {
    title: 'Preguntas Frecuentes | Mi Rubro',
    description:
        'Encontrá respuestas a las dudas más comunes sobre Mi Rubro, sus productos, la forma de uso, el soporte y el proceso de contacto.',
    alternates: { canonical: `${SITE_URL}/preguntas-frecuentes` },
    openGraph: {
        title: 'Preguntas Frecuentes | Mi Rubro',
        description:
            'Encontrá respuestas a las dudas más comunes sobre Mi Rubro, sus productos, la forma de uso, el soporte y el proceso de contacto.',
        url: `${SITE_URL}/preguntas-frecuentes`,
        siteName: 'Mirubro',
        type: 'website',
        locale: 'es_AR',
    },
    twitter: {
        card: 'summary',
        title: 'Preguntas Frecuentes | Mi Rubro',
        description:
            'Encontrá respuestas a las dudas más comunes sobre Mi Rubro, sus productos, la forma de uso, el soporte y el proceso de contacto.',
    },
};

/** JSON-LD FAQPage structured data */
function FAQJsonLd() {
    const items = FAQ_DATA.flatMap((cat) => cat.items);
    const schema = {
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        mainEntity: items.map((item) => ({
            '@type': 'Question',
            name: item.question,
            acceptedAnswer: {
                '@type': 'Answer',
                text: item.answer,
            },
        })),
    };
    return (
        <script
            type="application/ld+json"
            dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
        />
    );
}

export default function PreguntasFrecuentesPage() {
    return (
        <>
            <FAQJsonLd />

            {/* Hero */}
            <section className="border-b border-slate-200 bg-slate-50">
                <SiteContainer className="py-16 lg:py-20">
                    <div className="mx-auto max-w-2xl text-center">
                        <h1 className="font-display text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
                            Preguntas frecuentes
                        </h1>
                        <p className="mt-4 text-base leading-relaxed text-slate-600 sm:text-lg">
                            Respondemos las consultas más comunes sobre Mi Rubro, sus
                            productos, la implementación y el soporte.
                        </p>
                        <p className="mt-2 text-sm text-slate-500">
                            Si no encontrás lo que buscás, podés escribirnos y te ayudamos.
                        </p>
                    </div>
                </SiteContainer>
            </section>

            {/* FAQ body */}
            <SiteContainer className="py-16 lg:py-20">
                <div className="mx-auto max-w-3xl">
                    <FAQSearch data={FAQ_DATA} />

                    <div className="mt-14">
                        <FAQCTA />
                    </div>
                </div>
            </SiteContainer>
        </>
    );
}
