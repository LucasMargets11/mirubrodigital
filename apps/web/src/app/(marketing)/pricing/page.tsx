import type { Metadata } from 'next';
import { Suspense } from 'react';
import PricingClient from './pricing-client';

export const metadata: Metadata = {
    title: 'Planes y precios — Mirubro',
    description:
        'Planes flexibles para Gestión Comercial, Menú QR Online y QR de Reseñas. Precios transparentes que crecen con tu negocio.',
    alternates: { canonical: 'https://www.mirubro.com/pricing' },
    openGraph: {
        title: 'Planes y precios — Mirubro',
        description:
            'Planes flexibles para Gestión Comercial, Menú QR Online y QR de Reseñas. Precios transparentes que crecen con tu negocio.',
        url: 'https://www.mirubro.com/pricing',
        siteName: 'Mirubro',
        type: 'website',
        locale: 'es_AR',
    },
    twitter: {
        card: 'summary_large_image',
        title: 'Planes y precios — Mirubro',
        description:
            'Planes flexibles para Gestión Comercial, Menú QR Online y QR de Reseñas. Precios transparentes que crecen con tu negocio.',
    },
};

function PricingFallback() {
    return (
        <div className="bg-white min-h-screen">
            <div className="py-20 px-6 max-w-6xl mx-auto animate-pulse">
                <div className="text-center mb-16 space-y-4">
                    <div className="h-4 w-32 bg-slate-200 rounded mx-auto" />
                    <div className="h-10 w-80 bg-slate-200 rounded mx-auto" />
                    <div className="h-6 w-96 bg-slate-200 rounded mx-auto" />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-4xl mx-auto">
                    {[1, 2, 3].map((i) => (
                        <div key={i} className="h-32 bg-slate-100 rounded-2xl border border-slate-200" />
                    ))}
                </div>
            </div>
        </div>
    );
}

export default function PricingPage() {
    return (
        <Suspense fallback={<PricingFallback />}>
            <PricingClient />
        </Suspense>
    );
}
