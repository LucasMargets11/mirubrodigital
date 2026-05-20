import { cache } from 'react';
import { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { getServerApiBaseUrl, buildMediaUrl } from '@/lib/api-url';
import type { PublicReviewConfig } from '@/features/reviews/types';
import { ReviewFlowClient } from './review-flow-client';
import { ReviewLandingClient } from './review-landing-client';

// Fresh data on every request — config, threshold, redirect target can change.
export const dynamic = 'force-dynamic'
export const revalidate = 0

type Props = {
    params: Promise<{ slug: string }>;
};

const getReviewData = cache(async (slug: string) => {
    const apiBase = getServerApiBaseUrl();
    const res = await fetch(`${apiBase}/api/v1/reviews/public/${slug}/`, {
        cache: 'no-store',
    });
    if (!res.ok) return null;
    const data = await res.json() as PublicReviewConfig;
    return {
        ...data,
        logo_url: buildMediaUrl(data.logo_url),
    };
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

    if (data.effective_mode === 'direct') {
        return <ReviewLandingClient config={data} />;
    }

    return <ReviewFlowClient slug={slug} config={data} />;
}
