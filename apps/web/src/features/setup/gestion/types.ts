/**
 * Types for the Gestión Comercial Setup Center context
 * (GET /api/v1/setup/gestion/context).
 *
 * These are SEPARATE from the HelpModal's `StepStatus`/`StepStatusMap` types.
 * The backend returns richer statuses ('upgrade', 'upgrade_addon') that are
 * then collapsed to `'pending' | 'completed'` before being passed to HelpModal.
 */

/** Full status as returned by the backend — includes upgrade variants. */
export type SetupTaskStatus = 'completed' | 'pending' | 'upgrade' | 'upgrade_addon';

export interface SetupTask {
    status: SetupTaskStatus;
    detail: Record<string, unknown>;
}

export interface SetupPlan {
    /** Canonical plan code, e.g. 'starter' | 'pro' | 'business' | 'enterprise' */
    code: string;
    /** Human-readable plan name */
    name: string;
}

export interface SetupFeatures {
    products: boolean;
    inventory_basic: boolean;
    sales_basic: boolean;
    settings_basic: boolean;
    cash: boolean;
    treasury: boolean;
    invoices: boolean;
    rbac_full: boolean;
    multi_branch: boolean;
    tax_backup: boolean;
}

export interface SetupProgress {
    completed: number;
    total: number;
}

export interface GestionSetupContext {
    plan: SetupPlan;
    features: SetupFeatures;
    /** Keyed by full step ID, e.g. 'gestion.business_and_fiscal' */
    tasks: Record<string, SetupTask>;
    progress: SetupProgress;
    /**
     * Pre-collapsed status_map for HelpModal consumption.
     * Values are only 'completed' | 'pending' — upgrade variants are mapped to 'pending'.
     */
    status_map: Record<string, 'completed' | 'pending'>;
}
