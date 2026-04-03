/**
 * API client for Owner Access Management endpoints
 */
import { apiGet, apiPost, apiPut, apiPatch, apiDelete } from '@/lib/api/client';
import type {
    AccessSummary,
    AccountsListResponse,
    AuditLog,
    BulkPermissionUpdate,
    ChangeRoleResponse,
    CreateMemberPayload,
    CreateMemberResponse,
    DisableAccountResponse,
    PasswordResetResponse,
    PermissionUpdateResponse,
    RemoveMemberResponse,
    RoleDetail,
    RoleSummary,
    SuspendMemberResponse,
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
     * Get list of all user accounts in the business with seat info
     * Owner-only
     */
    getAccounts: () => apiGet<AccountsListResponse>(`${BASE}/accounts/?include_seat_info=1`),

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

    /**
     * Create an internal user (member) directly
     * Owner-only
     */
    createMember: (data: CreateMemberPayload) =>
        apiPost<CreateMemberResponse>(`${BASE}/accounts/create/`, data),

    /**
     * Change a member's role
     * Owner-only
     */
    changeRole: (userId: number, role: string) =>
        apiPatch<ChangeRoleResponse>(`${BASE}/accounts/${userId}/role/`, { role }),

    /**
     * Toggle suspend/reactivate a member's membership
     * Owner-only
     */
    suspendMember: (userId: number) =>
        apiPost<SuspendMemberResponse>(`${BASE}/accounts/${userId}/suspend/`),

    /**
     * Remove a member from the business
     * Owner-only
     */
    removeMember: (userId: number) =>
        apiDelete<RemoveMemberResponse>(`${BASE}/accounts/${userId}/`),

    /**
     * Reset password with optional explicit new password
     * Owner-only
     */
    resetPasswordWithPassword: (userId: number, newPassword: string) =>
        apiPost<PasswordResetResponse>(`${BASE}/accounts/${userId}/reset-password/`, { new_password: newPassword }),
};
