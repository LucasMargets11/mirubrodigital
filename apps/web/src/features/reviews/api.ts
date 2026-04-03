import { apiGet, apiPatch } from '@/lib/api/client';
import type { MenuEngagementSettings, MenuEngagementSettingsPayload } from '@/features/menu/types';

// Reuse existing engagement settings endpoint — QR Reviews users have manage_menu permission
export function getReviewSettings() {
    return apiGet<MenuEngagementSettings>('/api/v1/menu/engagement/');
}

export function updateReviewSettings(payload: MenuEngagementSettingsPayload) {
    return apiPatch<MenuEngagementSettings>('/api/v1/menu/engagement/', payload);
}

export type ReviewQrResponse = {
    business_id: number;
    slug: string;
    public_url: string;
    qr_svg: string;
    generated_at: string;
};

export function getReviewQrCode() {
    return apiGet<ReviewQrResponse>('/api/v1/reviews/qr/');
}

export type PublicReviewData = {
    business_name: string;
    review_url: string;
};

export function getPublicReviewData(slug: string) {
    return apiGet<PublicReviewData>(`/api/v1/menu/public/reviews/${slug}/`);
}
