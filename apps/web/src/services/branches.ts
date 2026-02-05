import { ApiError, apiGet, apiPost } from '@/lib/api/client';

export interface Branch {
    id: number;
    name: string;
    status: string;
    created_at: string;
}

export type CreateBranchPayload = {
    name: string;
};

export const branchService = {
    async list() {
        return apiGet<Branch[]>('/api/v1/branches/');
    },

    async create(payload: CreateBranchPayload) {
        try {
            return await apiPost<Branch>('/api/v1/branches/', payload);
        } catch (error) {
            throw normalizeApiError(error);
        }
    },
};

function normalizeApiError(error: unknown) {
    if (error instanceof ApiError) {
        return {
            response: {
                data: error.payload ?? { detail: error.message },
            },
            message: error.message,
        };
    }
    return error;
}
