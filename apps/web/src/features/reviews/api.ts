import { apiGet, apiPatch, apiPost } from '@/lib/api/client';
import type {
    ReviewConfig,
    ReviewConfigPayload,
    ReviewQrResponse,
    Review,
    ReviewStats,
    ReviewSubmitPayload,
    ReviewSubmitResponse,
} from './types';

/* ── Private (dashboard) endpoints ─────────────────────────── */

export function getReviewSettings() {
    return apiGet<ReviewConfig>('/api/v1/reviews/config/');
}

export function updateReviewSettings(payload: ReviewConfigPayload) {
    return apiPatch<ReviewConfig>('/api/v1/reviews/config/', payload);
}

export function getReviewQrCode() {
    return apiGet<ReviewQrResponse>('/api/v1/reviews/qr/');
}

export function getReviewStats() {
    return apiGet<ReviewStats>('/api/v1/reviews/stats/');
}

export function getReviews(params?: { status?: string; rating?: string; rating_min?: string; rating_max?: string; ordering?: string }) {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.rating) qs.set('rating', params.rating);
    if (params?.rating_min) qs.set('rating_min', params.rating_min);
    if (params?.rating_max) qs.set('rating_max', params.rating_max);
    if (params?.ordering) qs.set('ordering', params.ordering);
    const query = qs.toString();
    return apiGet<Review[]>(`/api/v1/reviews/${query ? `?${query}` : ''}`);
}

export function updateReviewStatus(id: string, status: string) {
    return apiPatch<Review>(`/api/v1/reviews/${id}/`, { status });
}

/* ── Public endpoints ──────────────────────────────────────── */

export function submitPublicReview(slug: string, payload: ReviewSubmitPayload) {
    return apiPost<ReviewSubmitResponse>(`/api/v1/reviews/public/${slug}/submit/`, payload);
}
