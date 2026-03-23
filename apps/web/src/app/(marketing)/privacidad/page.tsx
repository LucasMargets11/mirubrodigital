import type { Metadata } from 'next';
import { LegalPageLayout } from '@/components/legal/legal-page-layout';
import { privacySections, PRIVACY_LAST_UPDATED } from './_data';

const SITE_URL = 'https://www.mirubro.com';

export const metadata: Metadata = {
    title: 'Política de Privacidad | Mi Rubro',
    description:
        'Conocé cómo Mi Rubro recopila, utiliza y protege los datos personales vinculados al uso del sitio, contacto comercial y servicios digitales.',
    alternates: { canonical: `${SITE_URL}/privacidad` },
    openGraph: {
        title: 'Política de Privacidad | Mi Rubro',
        description:
            'Conocé cómo Mi Rubro recopila, utiliza y protege los datos personales vinculados al uso del sitio, contacto comercial y servicios digitales.',
        url: `${SITE_URL}/privacidad`,
        siteName: 'Mirubro',
        type: 'website',
        locale: 'es_AR',
    },
    twitter: {
        card: 'summary',
        title: 'Política de Privacidad | Mi Rubro',
        description:
            'Conocé cómo Mi Rubro recopila, utiliza y protege los datos personales vinculados al uso del sitio, contacto comercial y servicios digitales.',
    },
};

export default function PrivacidadPage() {
    return (
        <LegalPageLayout
            title="Política de Privacidad"
            subtitle={
                <>
                    En Mi Rubro respetamos la privacidad de las personas y protegemos los
                    datos personales que tratamos en el marco de nuestros servicios. Esta
                    Política de Privacidad explica qué información recopilamos, para qué la
                    usamos, con quién la compartimos y qué derechos tienen las personas
                    usuarias y clientes.
                </>
            }
            lastUpdated={PRIVACY_LAST_UPDATED}
            sections={privacySections}
            crossLink={{
                href: '/terminos' as never,
                label: 'Términos y Condiciones',
            }}
            footerNote="Plataforma desarrollada por Estudio VIZION."
        />
    );
}
