// features/onboarding/gestion/types.ts
// TypeScript contracts for the Gestión Comercial embedded onboarding wizard (MVP v1).

// ─── Step identifiers ─────────────────────────────────────────────────────────
export type GestionOnboardingStepId =
    | 'business_basics'
    | 'first_product'
    | 'sales_setup';

// ─── Step lifecycle states ────────────────────────────────────────────────────
export type GestionOnboardingStepStatus =
    | 'locked'           // feature not available in plan (post-MVP)
    | 'pending'          // not started, available
    | 'in_progress'      // frontend-only, currently active step
    | 'completed'        // done (from real data or completed_at)
    | 'skipped'          // explicitly skipped by user
    | 'needs_attention'; // data inconsistency (post-MVP)

// ─── Step descriptor ──────────────────────────────────────────────────────────
export interface GestionOnboardingStep {
    id: GestionOnboardingStepId;
    status: GestionOnboardingStepStatus;
    required: boolean;   // wizard blocks "Finalizar" until completed or skipped
    skippable: boolean;  // shows "Saltar este paso" button
}

// ─── Persisted progress ───────────────────────────────────────────────────────
export interface GestionOnboardingProgress {
    product_type: 'gestion';
    version: 'v1';
    current_step: GestionOnboardingStepId | '';  // '' = not started / done
    skipped_steps: GestionOnboardingStepId[];
    completed_at: string | null;   // ISO 8601
    dismissed_at: string | null;   // ISO 8601
}

// ─── Full context response ────────────────────────────────────────────────────
export interface GestionOnboardingContext {
    business: {
        id: number;
        name: string;
        status: 'onboarding' | 'trialing' | 'active' | 'past_due' | 'suspended' | 'canceled';
    };
    plan: {
        code: 'starter' | 'pro' | 'business' | 'enterprise';
        name: string;
        is_trial: boolean;
    };
    features: {
        products: boolean;
        inventory_basic: boolean;
        sales_basic: boolean;
        settings_basic: boolean;
        cash: boolean;
        customers: boolean;
    };
    user_role: 'owner' | 'admin' | 'manager' | 'seller' | 'viewer' | 'staff';
    business_basics: {
        name: string;
        trade_name: string;
        phone: string;
        email: string;
    };
    catalog: {
        products_count: number;
        categories_count: number;
    };
    sales: {
        sales_count: number;
        first_sale_at: string | null;
    };
    commercial_settings: {
        allow_sell_without_stock: boolean;
        block_sales_if_no_open_cash_session: boolean;
        require_customer_for_sales: boolean;
    };
    progress: GestionOnboardingProgress;
    steps: GestionOnboardingStep[];
}

// ─── API payloads ─────────────────────────────────────────────────────────────
export interface BusinessBasicsPayload {
    business_name: string;       // min 2, max 120
    phone?: string | null;
    email?: string | null;
}

export interface FirstProductPayload {
    name: string;                // min 2 chars
    price: string;               // decimal string >= "0"
    cost?: string | null;
    category_id?: string | null; // UUID string
    category_name?: string | null;
    initial_stock?: string | null; // decimal string >= "0", null / "0" = no movement
}

// sales-setup: no user input
export type SalesSetupPayload = Record<string, never>;

export interface SkipStepPayload {
    step_id: GestionOnboardingStepId;
}

// ─── API response shapes ──────────────────────────────────────────────────────
export interface OnboardingStepResponse {
    progress: GestionOnboardingProgress;
    steps: GestionOnboardingStep[];
}

export interface FirstProductResponse extends GestionOnboardingContext {
    product: {
        id: string;
        name: string;
        price: string;
        cost: string | null;
        sku: string | null;
        category: { id: string; name: string } | null;
    };
    stock_movement: {
        id: string;
        quantity: string;
        movement_type: 'IN';
    } | null;
}

export interface SalesSetupResponse extends OnboardingStepResponse {
    commercial_settings: {
        allow_sell_without_stock: boolean;
        block_sales_if_no_open_cash_session: boolean;
        require_customer_for_sales: boolean;
    };
    warning?: string;
}

export interface DismissResponse {
    progress: GestionOnboardingProgress;
}
