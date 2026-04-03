import { cache } from 'react';
import { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { getServerApiBaseUrl } from '@/lib/api-url';
import { ReviewLandingClient } from './review-landing-client';

type Props = {
    params: Promise<{ slug: string }>;
};

const getReviewData = cache(async (slug: string) => {
    const apiBase = getServerApiBaseUrl();
    const res = await fetch(`${apiBase}/api/v1/menu/public/reviews/${slug}/`, {
        cache: 'no-store',
    });
    if (!res.ok) return null;
    return res.json() as Promise<{ business_name: string; review_url: string }>;
});

export async function generateMetadata({ params }: Props): Promise<Metadata> {
    const { slug } = await params;
    const data = await getReviewData(slug);
    if (!data) {
        return { title: 'Reseña no encontrada' };
    }
    return {
        title: `Dejá tu reseña — ${data.business_name}`,
        description: `Contanos tu experiencia en ${data.business_name}.`,
    };
}

export default async function ReviewLandingPage({ params }: Props) {
    const { slug } = await params;
    const data = await getReviewData(slug);

    if (!data) {
        notFound();
    }

    return (
        <ReviewLandingClient
            businessName={data.business_name}
            reviewUrl={data.review_url}
        />
    );
}
