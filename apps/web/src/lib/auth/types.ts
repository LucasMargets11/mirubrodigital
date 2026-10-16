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

export type PublicBookingUnavailableReason = 'missing_slug' | 'service_disabled' | 'not_publishable';

export type PublicBookingPage = {
  available: boolean;
  /** URL absoluta `…/t/<slug>`; solo presente cuando `available`. */
  url: string | null;
  reason: PublicBookingUnavailableReason | null;
};

export type Session = {
  user: {
    id: number;
    email: string;
    name: string;
    /** Whether the user has verified their email address. */
    email_verified: boolean;
    /** Account mode: 'owner_managed' or 'personal'. */
    account_mode: 'owner_managed' | 'personal';
    /** Whether the user must change their password before accessing the app. */
    must_change_password: boolean;
    /** Method used for initial registration ('email' | 'google'). */
    auth_provider?: 'email' | 'google';
    /** Whether the user has linked a Google account. */
    has_google_linked?: boolean;
    /** Whether the user has a usable password set. */
    has_password?: boolean;
  };
  memberships: MembershipSummary[];
  current: {
    business: {
      id: number;
      name: string;
      /**
       * Business lifecycle status (mirrors Business.status on the backend).
       * 'onboarding' — business created, no active subscription yet.
       * 'trialing'   — trial period active, access allowed (Wave 3).
       * 'active'     — subscription confirmed, normal operations.
       * 'past_due'   — renewal failed, grace period active (Wave 3).
       * 'suspended'  — billing hard-block.
       * 'canceled'   — subscription terminated.
       */
      status: 'onboarding' | 'trialing' | 'active' | 'past_due' | 'suspended' | 'canceled';
      /**
       * Página pública de reservas de Turnos (`/t/<slug>`), calculada por el
       * backend con la misma regla que el endpoint público. `null` si el
       * Business no tiene Turnos habilitado.
       */
      public_booking?: PublicBookingPage | null;
      /**
       * Zona horaria IANA canónica del Business (Slice 7D.1), ya resuelta por
       * el backend con su fallback (`settings.TIME_ZONE`). Solo lectura.
       */
      timezone?: string;
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
