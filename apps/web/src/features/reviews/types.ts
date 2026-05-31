/* ── Reviews domain types ─────────────────────────────────── */

export type ReviewMode = 'direct' | 'smart_filter';

/** Private config returned by GET /api/v1/reviews/config/ */
export interface ReviewConfig {
    enabled: boolean;
    google_place_id: string;
    google_place_name: string;
    google_place_formatted_address: string;
    google_place_updated_at: string | null;
    google_review_url: string;
    custom_redirect_url: string;
    redirect_threshold: number;
    collect_contact: boolean;
    thank_you_message: string;
    public_display_name: string;
    public_subtitle: string;
    public_question: string;
    redirect_url: string; // read-only computed
    mode: ReviewMode;
    effective_mode: ReviewMode;
    trial_ends_at: string | null;
    trial_used: boolean;
    smart_filter_allowed: boolean;
    is_reviews_pro: boolean;
    trial_active: boolean;
    trial_available: boolean;
    updated_at: string;
}

/** Response from POST /api/v1/reviews/trial/activate/ — returns full ReviewConfig */
export type TrialActivationResponse = ReviewConfig;

/** Payload accepted by PATCH /api/v1/reviews/config/ */
export interface ReviewConfigPayload {
    enabled?: boolean;
    google_place_id?: string;
    google_place_name?: string;
    google_place_formatted_address?: string;
    google_review_url?: string;
    custom_redirect_url?: string;
    redirect_threshold?: number;
    collect_contact?: boolean;
    thank_you_message?: string;
    public_display_name?: string;
    public_subtitle?: string;
    public_question?: string;
    mode?: ReviewMode;
}

/** Public config returned by GET /api/v1/reviews/public/<slug>/ */
export interface PublicReviewConfig {
    business_name: string;
    display_name: string;
    subtitle: string;
    question: string;
    redirect_url: string;
    redirect_threshold: number;
    collect_contact: boolean;
    thank_you_message: string;
    enabled: boolean;
    mode: ReviewMode;
    effective_mode: ReviewMode;
    logo_url: string | null;
    accent_color: string | null;
    is_pro: boolean;
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
    effective_mode: ReviewMode;
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
    visits_last_7_days: number;
    visits_last_30_days: number;
    daily_trend: { date: string; count: number }[];
    redirect_threshold: number;
    effective_mode: ReviewMode;
}
