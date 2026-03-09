export type FeatureFlags = Record<string, boolean>;
export type PermissionMap = Record<string, boolean>;

export type MembershipSummary = {
  business: {
    id: number;
    name: string;
  };
  role: string;
  service: string;
};

export type ServiceDefinition = {
  slug: string;
  name: string;
  description: string;
  features: string[];
  min_plan: string;
};

export type ServicesSnapshot = {
  available: ServiceDefinition[];
  enabled: string[];
  default: string | null;
};

/**
 * Subscription enforcement reason codes (mirrors billing.enforcement.ReasonCode).
 * Used by frontend to render appropriate UI for each billing state.
 */
export type SubscriptionReasonCode =
  | 'access_granted'
  | 'grace_period_active'
  | 'grace_period_expired'
  | 'trial_expired'
  | 'suspended'
  | 'canceled'
  | 'checkout_pending'
  | 'no_subscription';

export type Session = {
  user: {
    id: number;
    email: string;
    name: string;
  };
  memberships: MembershipSummary[];
  current: {
    business: {
      id: number;
      name: string;
    };
    role: string;
    service: string;
  };
  subscription: {
    plan: string;
    status: string;
    /** Mirrors billing.enforcement.get_enforcement_decision().access_allowed */
    access_allowed: boolean;
    /** Machine-readable reason code for the enforcement decision */
    reason_code: SubscriptionReasonCode;
    /** ISO datetime string when grace period expires (PAST_DUE only) */
    grace_until: string | null;
    /** ISO datetime string until access is guaranteed (best-effort) */
    access_until: string | null;
    /** True when frontend should show a renewal/regularization prompt */
    show_renewal_prompt: boolean;
    /** Subscription source: 'v2' | 'legacy' | 'none' */
    source: string;
  };
  services: ServicesSnapshot;
  features: FeatureFlags;
  permissions: PermissionMap;
};
