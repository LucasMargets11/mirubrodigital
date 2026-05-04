import type { Metadata } from 'next';
import { FinalCtaSection } from '@/components/marketing/sections/final-cta';
import { HeroSection } from '@/components/marketing/sections/hero';
import { HomeProductShowcase } from '@/components/marketing/sections/home-product-showcase';
import { ProductsSection } from '@/components/marketing/sections/products';
import { BlogResourcesSection } from '@/components/marketing/sections/blog-resources';
import { ExpandingPanelSection } from '@/components/marketing/sections/expanding-panel';

const SITE_URL = 'https://www.mirubro.com';

export const metadata: Metadata = {
    title: 'MiRubro — Gestión comercial, Carta QR y Reseñas',
    description:
        'Plataforma digital para gestionar tu negocio con herramientas de gestión comercial, carta online, operación gastronómica y QR de reseñas.',
    alternates: {
        canonical: SITE_URL,
    },
    openGraph: {
        title: 'MiRubro — Gestión comercial, Carta QR y Reseñas',
        description:
            'Plataforma digital para gestionar tu negocio con herramientas de gestión comercial, carta online, operación gastronómica y QR de reseñas.',
        url: SITE_URL,
        siteName: 'MiRubro',
        type: 'website',
        locale: 'es_AR',
    },
    twitter: {
        card: 'summary_large_image',
        title: 'MiRubro — Gestión comercial, Carta QR y Reseñas',
        description:
            'Plataforma digital para gestionar tu negocio con herramientas de gestión comercial, carta online, operación gastronómica y QR de reseñas.',
    },
};

/** JSON-LD: Organization — core business identity for Google Knowledge Panel. */
function OrganizationJsonLd() {
    const schema = {
        '@context': 'https://schema.org',
        '@type': 'Organization',
        name: 'Mirubro',
        url: SITE_URL,
        logo: `${SITE_URL}/logo/rubroicono.png`,
        description:
            'Software de gestión para comercios y gastronomía. Inventario, ventas, caja, carta digital y más.',
        sameAs: ['https://www.instagram.com/mirubrodigital/'],
        contactPoint: {
            '@type': 'ContactPoint',
            contactType: 'customer service',
            url: `${SITE_URL}/contacto`,
        },
    };
    return (
        <script
            type="application/ld+json"
            dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
        />
    );
}

/** JSON-LD: WebSite — helps Google understand site identity and URL structure. */
function WebSiteJsonLd() {
    const schema = {
        '@context': 'https://schema.org',
        '@type': 'WebSite',
        name: 'Mirubro',
        url: SITE_URL,
        publisher: { '@type': 'Organization', name: 'Mirubro', url: SITE_URL },
    };
    return (
        <script
            type="application/ld+json"
            dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
        />
    );
}

export default function MarketingHomePage() {
    return (
        <>
            <OrganizationJsonLd />
            <WebSiteJsonLd />
            <HeroSection />
            <HomeProductShowcase />
            <BlogResourcesSection />
            <ExpandingPanelSection />
            <ProductsSection />
            <FinalCtaSection />
        </>
    );
}
