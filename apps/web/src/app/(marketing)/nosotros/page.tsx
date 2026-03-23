import type { Metadata } from 'next';
import { AboutHero } from './_components/AboutHero';
import { AboutWhatIs } from './_components/AboutWhatIs';
import { AboutProblemSection } from './_components/AboutProblemSection';
import { AboutProductsSection } from './_components/AboutProductsSection';
import { AboutProcessSection } from './_components/AboutProcessSection';
import { AboutWhyChoose } from './_components/AboutWhyChoose';
import { AboutVizionSection } from './_components/AboutVizionSection';
import { AboutCTA } from './_components/AboutCTA';

const SITE_URL = 'https://www.mirubro.com';

export const metadata: Metadata = {
    title: 'Nosotros | Mi Rubro',
    description:
        'Conocé Mi Rubro: herramientas digitales para comercios, locales gastronómicos y negocios. Desarrollado por Estudio VIZION.',
    alternates: { canonical: `${SITE_URL}/nosotros` },
    openGraph: {
        title: 'Nosotros | Mi Rubro',
        description:
            'Conocé Mi Rubro: herramientas digitales para comercios, locales gastronómicos y negocios. Desarrollado por Estudio VIZION.',
        url: `${SITE_URL}/nosotros`,
        siteName: 'Mirubro',
        type: 'website',
        locale: 'es_AR',
    },
    twitter: {
        card: 'summary',
        title: 'Nosotros | Mi Rubro',
        description:
            'Conocé Mi Rubro: herramientas digitales para comercios, locales gastronómicos y negocios. Desarrollado por Estudio VIZION.',
    },
};

export default function NosotrosPage() {
    return (
        <>
            <AboutHero />
            <AboutWhatIs />
            <AboutProblemSection />
            <AboutProductsSection />
            <AboutProcessSection />
            <AboutWhyChoose />
            <AboutVizionSection />
            <AboutCTA />
        </>
    );
}
