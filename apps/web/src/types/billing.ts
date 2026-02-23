// Types for Commercial Subscription API responses

export interface PlanPricing {
    monthly: number;
    yearly: number;
}

export interface CurrentPlan {
    code: string;
    name: string;
    description: string;
    pricing: PlanPricing;
    features: string[];
    is_custom: boolean;
}

export interface BranchesInfo {
    used: number;
    included: number;
    extras_qty: number;
    max_total: number | null;
    can_add_more: boolean;
    remaining: number | null;
    unit_pricing: PlanPricing;
}

export interface SeatsInfo {
    included: number;
    extras_qty: number;
    total: number;
    unit_pricing: PlanPricing;
}

export interface AddonInfo {
    code: string;
    name: string;
    description: string;
    pricing: PlanPricing;
}

export interface AddonsInfo {
    active: AddonInfo[];
    available: AddonInfo[];
    included: AddonInfo[];
}

export interface CommercialSubscription {
    current_plan: CurrentPlan;
    billing_cycle: 'monthly' | 'yearly';
    branches: BranchesInfo;
    seats: SeatsInfo;
    addons: AddonsInfo;
    can_manage: boolean;
}

export interface PreviewLineItem {
    description: string;
    quantity: number;
    unit_price: number;
    total: number;
    is_recurring: boolean;
}

export interface ValidationError {
    field: string;
    message: string;
}

export interface PreviewChangeRequest {
    plan_code: string;
    billing_cycle: 'monthly' | 'yearly';
    crm: boolean;
    invoicing: boolean;
    branches_extra_qty: number;
    seats_extra_qty: number;
}

export interface PreviewChangeResponse {
    line_items: PreviewLineItem[];
    subtotal: number;
    total_now: number;
    total_recurring: number;
    requires_checkout: boolean;
    is_upgrade: boolean;
    is_downgrade: boolean;
    validation_errors: ValidationError[];
    change_summary: string;
}

export interface CheckoutResponse {
    pending_change_id: number;
    checkout_url?: string;
    requires_payment: boolean;
    applied?: boolean;
    scheduled?: boolean;
    message: string;
}

export interface AddonCheckoutRequest {
    addon_code: string;
    billing_cycle: 'monthly' | 'yearly';
}

export interface AddonCheckoutResponse {
    pending_change_id: number;
    checkout_url: string;
    requires_payment: boolean;
    addon: {
        code: string;
        name: string;
        description: string;
    };
    price: number;
    billing_cycle: 'monthly' | 'yearly';
    message: string;
}
