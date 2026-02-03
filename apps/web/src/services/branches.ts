import axios from 'axios';
import { getCookie } from 'cookies-next';
import { API_URL } from '@/lib/api-url';

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
        const token = getCookie('access_token');
        const response = await axios.get<Branch[]>(`${API_URL}/api/v1/business/branches/`, {
            headers: { Authorization: `Bearer ${token}` },
            withCredentials: true,
        });
        return response.data;
    },

    async create(payload: CreateBranchPayload) {
        const token = getCookie('access_token');
        const response = await axios.post<Branch>(`${API_URL}/api/v1/business/branches/`, payload, {
            headers: { Authorization: `Bearer ${token}` },
            withCredentials: true,
        });
        return response.data;
    },
};
