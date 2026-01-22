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
  };
  services: ServicesSnapshot;
  features: FeatureFlags;
  permissions: PermissionMap;
};
