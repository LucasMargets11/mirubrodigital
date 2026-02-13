/**
 * API client for Owner Access Management endpoints
 */
import { apiGet, apiPost, apiPut } from '@/lib/api/client';
import type {
    AccessSummary,
    AuditLog,
    BulkPermissionUpdate,
    DisableAccountResponse,
    PasswordResetResponse,
    PermissionUpdateResponse,
    RoleDetail,
    RoleSummary,
    UserAccount,
} from '@/types/owner-access';

const BASE = '/api/v1/owner/access';

export const ownerAccessApi = {
    /**
     * Get current user's access summary with roles and permissions
     */
    getAccessSummary: () => apiGet<AccessSummary>(`${BASE}/summary/`),

    /**
     * Get list of all roles in the business with user counts
     * Owner-only
     */
    getRoles: () => apiGet<RoleSummary[]>(`${BASE}/roles/`),

    /**
     * Get detailed information about a specific role
     * Owner-only
     */
    getRoleDetail: (role: string) => apiGet<RoleDetail>(`${BASE}/roles/${role}/`),

    /**
     * Get list of all user accounts in the business
     * Owner-only
     */
    getAccounts: () => apiGet<UserAccount[]>(`${BASE}/accounts/`),

    /**
     * Reset a user's password and get temporary password (shown only once)
     * Owner-only
     */
    resetPassword: (userId: number) => apiPost<PasswordResetResponse>(`${BASE}/accounts/${userId}/reset-password/`),

    /**
     * Enable/disable a user account
     * Owner-only
     */
    toggleAccount: (userId: number) => apiPost<DisableAccountResponse>(`${BASE}/accounts/${userId}/disable/`),

    /**
     * Get audit logs of access management actions
     * Owner-only
     */
    getAuditLogs: (params?: { limit?: number; user_id?: number }) => {
        const query = new URLSearchParams();
        if (params?.limit) query.set('limit', params.limit.toString());
        if (params?.user_id) query.set('user_id', params.user_id.toString());
        const queryString = query.toString();
        return apiGet<AuditLog[]>(`${BASE}/audit-logs/${queryString ? `?${queryString}` : ''}`);
    },

    /**
     * Update permissions for a specific role
     * Owner-only
     */
    updateRolePermissions: (role: string, data: BulkPermissionUpdate) => 
        apiPut<PermissionUpdateResponse>(`${BASE}/roles/${role}/permissions/`, data),
};
