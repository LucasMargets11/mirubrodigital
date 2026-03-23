export type SubscriptionStatus =
    | 'checkout_pending'
    | 'trialing'
    | 'active'
    | 'past_due'
    | 'suspended'
    | 'canceled';

export interface SubscriptionInfo {
    id: string;
    plan_code: string;
    plan_name: string;
    service_type: string;
    status: SubscriptionStatus;
    status_display: string;
    provider: string;
    current_period_start: string | null;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
    cancel_requested_at: string | null;
    cancel_effective_at: string | null;
    cancel_reason: string;
    canceled_at: string | null;
    is_active: boolean;
    created_at: string;
    /** 'v2' | 'legacy' — indicates the subscription source */
    source: string;
    /** Whether this subscription supports cancel/undo via the API */
    can_manage_cancellation: boolean;
    /** Plan limits (legacy subscriptions) */
    max_seats?: number | null;
    max_branches?: number | null;
}

export interface SubscriptionStatusResponse {
    has_subscription: boolean;
    subscription: SubscriptionInfo | null;
    role: string;
}

export interface CancelSubscriptionResponse {
    detail: string;
    subscription: SubscriptionInfo;
}
