import { cache } from 'react';
import { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { getServerApiBaseUrl } from '@/lib/api-url';
import type { PublicReviewConfig } from '@/features/reviews/types';
import { ReviewFlowClient } from './review-flow-client';

type Props = {
    params: Promise<{ slug: string }>;
};

const getReviewData = cache(async (slug: string) => {
    const apiBase = getServerApiBaseUrl();
    const res = await fetch(`${apiBase}/api/v1/reviews/public/${slug}/`, {
        cache: 'no-store',
    });
    if (!res.ok) return null;
    return res.json() as Promise<PublicReviewConfig>;
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

    if (!data || !data.enabled) {
        notFound();
    }

    return <ReviewFlowClient slug={slug} config={data} />;
}
