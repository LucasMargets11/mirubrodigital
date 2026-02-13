/**
 * Types for Owner Access Management feature
 */

export interface Capability {
  code: string;
  title: string;
  description: string;
  module: string;
  service: string;
  granted?: boolean;
}

export interface PermissionsByModule {
  [module: string]: Capability[];
}

export interface RoleSummary {
  role: string;
  role_display: string;
  user_count: number;
  permission_count: number;
}

export interface UserAccount {
  id: number;
  email: string;
  username: string;
  full_name: string;
  role: string;
  role_display: string;
  is_active: boolean;
  has_usable_password: boolean;
  date_joined: string;
  last_login: string | null;
}

export interface RoleDetail {
  role: string;
  role_display: string;
  description: string;
  service: string;
  permissions_by_module: PermissionsByModule;
  users: UserAccount[];
}

export interface AccessSummary {
  user_id: number;
  role: string;
  role_display: string;
  business_name: string;
  service: string;
  permissions_by_module: PermissionsByModule;
}

export interface PasswordResetResponse {
  success: boolean;
  message: string;
  temporary_password?: string;
  username: string;
  email: string;
}

export interface AuditLog {
  id: number;
  action: string;
  actor_email: string | null;
  actor_name: string;
  target_email: string;
  target_name: string;
  details: Record<string, any>;
  ip_address: string | null;
  created_at: string;
}

export interface DisableAccountResponse {
  success: boolean;
  message: string;
  is_active: boolean;
}

export interface PermissionUpdate {
  permission: string;
  enabled: boolean;
}

export interface BulkPermissionUpdate {
  permissions: PermissionUpdate[];
}

export interface PermissionUpdateResponse {
  success: boolean;
  message: string;
  role: string;
  service: string;
  updated_count: number;
  permissions_by_module: PermissionsByModule;
}
