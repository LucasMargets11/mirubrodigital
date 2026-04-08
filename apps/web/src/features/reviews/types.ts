/* ── Reviews domain types ─────────────────────────────────── */

/** Private config returned by GET /api/v1/reviews/config/ */
export interface ReviewConfig {
    enabled: boolean;
    google_place_id: string;
    google_review_url: string;
    custom_redirect_url: string;
    redirect_threshold: number;
    collect_contact: boolean;
    thank_you_message: string;
    redirect_url: string; // read-only computed
    updated_at: string;
}

/** Payload accepted by PATCH /api/v1/reviews/config/ */
export interface ReviewConfigPayload {
    enabled?: boolean;
    google_place_id?: string;
    google_review_url?: string;
    custom_redirect_url?: string;
    redirect_threshold?: number;
    collect_contact?: boolean;
    thank_you_message?: string;
}

/** Public config returned by GET /api/v1/reviews/public/<slug>/ */
export interface PublicReviewConfig {
    business_name: string;
    redirect_url: string;
    redirect_threshold: number;
    collect_contact: boolean;
    thank_you_message: string;
    enabled: boolean;
}

/** Payload for POST /api/v1/reviews/public/<slug>/submit/ */
export interface ReviewSubmitPayload {
    rating: number;
    comment?: string;
    contact_info?: string;
    source?: 'qr' | 'menu' | 'direct';
}

/** Response from POST /api/v1/reviews/public/<slug>/submit/ */
export interface ReviewSubmitResponse {
    action: 'redirect' | 'submitted';
    redirect_url?: string;
    message: string;
}

export type ReviewStatus = 'new' | 'read' | 'contacted' | 'resolved';
export type ReviewSource = 'qr' | 'menu' | 'direct';

/** Review item returned by GET /api/v1/reviews/ */
export interface Review {
    id: string;
    rating: number;
    comment: string;
    contact_info: string;
    source: ReviewSource;
    status: ReviewStatus;
    created_at: string;
}

/** QR code response from GET /api/v1/reviews/qr/ */
export interface ReviewQrResponse {
    slug: string;
    public_url: string;
    qr_svg: string;
    generated_at: string;
}

/** Analytics stats from GET /api/v1/reviews/stats/ */
export interface ReviewStats {
    total_reviews: number;
    average_rating: number;
    total_visits: number;
    conversion_rate: number;
    positive_reviews: number;
    negative_reviews: number;
    positive_rate: number;
    negative_rate: number;
    new_reviews: number;
    contacted_reviews: number;
    resolved_reviews: number;
    resolution_rate: number;
    rating_distribution: Record<string, number>;
    status_distribution: Record<string, number>;
    recent_reviews: Review[];
    reviews_last_7_days: number;
    reviews_last_30_days: number;
}
