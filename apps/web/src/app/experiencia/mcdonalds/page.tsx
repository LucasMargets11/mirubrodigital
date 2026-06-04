import type { Metadata } from 'next';

import { McDonaldsExperienceSurvey } from '@/features/public-surveys/McDonaldsExperienceSurvey';

// Demo pública — accesible por link directo, pero no indexable.
export const metadata: Metadata = {
    title: 'McDonald’s Sucursal | Experiencia del cliente',
    description:
        'Encuesta mobile de satisfacción para clientes de McDonald’s Recoleta.',
    robots: {
        index: false,
        follow: false,
        googleBot: { index: false, follow: false },
    },
};

export default function McDonaldsExperiencePage() {
    return <McDonaldsExperienceSurvey />;
}
