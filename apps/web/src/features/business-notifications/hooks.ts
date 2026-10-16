import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError } from '@/lib/api/client';

import { fetchBusinessNotifications, markBusinessNotificationRead } from './api';

const baseKey = ['business-notifications'];

export function useUnreadBusinessNotifications(limit = 5) {
    return useQuery({
        queryKey: [...baseKey, 'unread', limit],
        queryFn: () => fetchBusinessNotifications({ unread: true, limit }),
        refetchInterval: 60_000,
        // 403 = el rol no recibe notificaciones: no reintentar.
        retry: (count, error) => !(error instanceof ApiError && error.status === 403) && count < 2,
    });
}

export function useMarkBusinessNotificationRead() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (id: string) => markBusinessNotificationRead(id),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: baseKey }),
    });
}
