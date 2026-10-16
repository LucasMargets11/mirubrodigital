import { apiGet, apiPost } from '@/lib/api/client';

import type { BusinessNotification, BusinessNotificationList } from './types';

const BASE = '/api/v1/notifications/business/';

export function fetchBusinessNotifications(params: { unread?: boolean; limit?: number } = {}) {
    const search = new URLSearchParams();
    if (params.unread) search.set('unread', 'true');
    if (params.limit) search.set('limit', String(params.limit));
    const query = search.toString();
    return apiGet<BusinessNotificationList>(`${BASE}${query ? `?${query}` : ''}`);
}

export function markBusinessNotificationRead(id: string) {
    return apiPost<BusinessNotification>(`${BASE}${encodeURIComponent(id)}/read/`, {});
}

/** Solo rutas internas del panel; cualquier otra cosa no se enlaza. */
export function safeInternalHref(url: string | null | undefined): string | null {
    if (!url || !url.startsWith('/app/') || url.startsWith('//') || url.includes('\\')) return null;
    return url;
}
