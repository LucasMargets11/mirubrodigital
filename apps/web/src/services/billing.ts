import { apiPost } from '@/lib/api/client';
import type { PreviewChangeRequest, PreviewChangeResponse, CheckoutResponse, AddonCheckoutRequest, AddonCheckoutResponse } from '@/types/billing';

export async function previewSubscriptionChange(request: PreviewChangeRequest): Promise<PreviewChangeResponse> {
    return apiPost<PreviewChangeResponse>('/api/v1/billing/commercial/preview-change/', request);
}

export async function checkoutSubscriptionChange(request: PreviewChangeRequest): Promise<CheckoutResponse> {
    return apiPost<CheckoutResponse>('/api/v1/billing/commercial/checkout/', request);
}

export async function checkoutAddonPurchase(request: AddonCheckoutRequest): Promise<AddonCheckoutResponse> {
    return apiPost<AddonCheckoutResponse>('/api/v1/billing/commercial/addon-checkout/', request);
}
