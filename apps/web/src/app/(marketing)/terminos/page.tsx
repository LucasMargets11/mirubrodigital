import type { Metadata } from 'next';
import { LegalPageLayout } from '@/components/legal/legal-page-layout';
import { termsSections, TERMS_LAST_UPDATED } from './_data';

const SITE_URL = 'https://www.mirubro.com';

export const metadata: Metadata = {
    title: 'Términos y Condiciones | Mi Rubro',
    description:
        'Leé los términos y condiciones de uso de Mi Rubro para conocer el alcance de los servicios, las reglas de uso y las condiciones generales aplicables.',
    alternates: { canonical: `${SITE_URL}/terminos` },
    openGraph: {
        title: 'Términos y Condiciones | Mi Rubro',
        description:
            'Leé los términos y condiciones de uso de Mi Rubro para conocer el alcance de los servicios, las reglas de uso y las condiciones generales aplicables.',
        url: `${SITE_URL}/terminos`,
        siteName: 'Mirubro',
        type: 'website',
        locale: 'es_AR',
    },
    twitter: {
        card: 'summary',
        title: 'Términos y Condiciones | Mi Rubro',
        description:
            'Leé los términos y condiciones de uso de Mi Rubro para conocer el alcance de los servicios, las reglas de uso y las condiciones generales aplicables.',
    },
};

export default function TerminosPage() {
    return (
        <LegalPageLayout
            title="Términos y Condiciones"
            subtitle={
                <>
                    Estos Términos y Condiciones regulan el acceso y uso del sitio web y de
                    los servicios ofrecidos bajo la marca Mi Rubro. Al acceder al sitio,
                    solicitar una demo, registrarte o contratar cualquiera de nuestros
                    servicios, aceptás estos términos.
                </>
            }
            lastUpdated={TERMS_LAST_UPDATED}
            sections={termsSections}
            crossLink={{
                href: '/privacidad' as never,
                label: 'Política de Privacidad',
            }}
        />
    );
}
