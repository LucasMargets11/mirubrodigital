import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from './client';

export const api = {
  async get<T>(path: string) {
    const data = await apiGet<T>(path);
    return { data };
  },

  async post<T>(path: string, body?: unknown) {
    const data = await apiPost<T>(path, body);
    return { data };
  },

  async put<T>(path: string, body?: unknown) {
    const data = await apiPut<T>(path, body);
    return { data };
  },

  async patch<T>(path: string, body?: unknown) {
    const data = await apiPatch<T>(path, body);
    return { data };
  },

  async delete<T>(path: string) {
    const data = await apiDelete<T>(path);
    return { data };
  },
};

export * from './client';
