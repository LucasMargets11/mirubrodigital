import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '@/lib/api/client';
import type {
    SubscriptionStatusResponse,
    CancelSubscriptionResponse,
} from './subscription-types';

const subscriptionStatusKey = ['billing', 'subscription-status'];

export function useSubscriptionStatusQuery() {
    return useQuery({
        queryKey: subscriptionStatusKey,
        queryFn: () =>
            apiGet<SubscriptionStatusResponse>('/api/v1/billing/subscription-status/'),
        staleTime: 60_000,
        retry: (failureCount, error) => {
            if ((error as { status?: number })?.status === 403) return false;
            return failureCount < 3;
        },
    });
}

export function useCancelSubscriptionMutation() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (reason?: string) =>
            apiPost<CancelSubscriptionResponse>('/api/v1/billing/cancel-subscription/', {
                reason: reason || '',
            }),
        onSuccess: (data) => {
            queryClient.setQueryData<SubscriptionStatusResponse>(subscriptionStatusKey, (old) => ({
                has_subscription: true,
                subscription: data.subscription,
                role: old?.role ?? 'owner',
            }));
        },
    });
}

export function useUndoCancelSubscriptionMutation() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: () =>
            apiPost<CancelSubscriptionResponse>('/api/v1/billing/undo-cancel/'),
        onSuccess: (data) => {
            queryClient.setQueryData<SubscriptionStatusResponse>(subscriptionStatusKey, (old) => ({
                has_subscription: true,
                subscription: data.subscription,
                role: old?.role ?? 'owner',
            }));
        },
    });
}
