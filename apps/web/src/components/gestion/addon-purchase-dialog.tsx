'use client';

import { useState } from 'react';
import { Loader2, AlertCircle, CheckCircle, Sparkles, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { AddonInfo, CommercialSubscription } from '@/types/billing';

interface AddonPurchaseDialogProps {
    addon: AddonInfo;
    subscription: CommercialSubscription;
    onClose: () => void;
    onConfirm: (addonCode: string, billingCycle: 'monthly' | 'yearly') => Promise<void>;
}

function formatPrice(cents: number): string {
    return `$${(cents / 100).toFixed(0)}`;
}

export function AddonPurchaseDialog({
    addon,
    subscription,
    onClose,
    onConfirm,
}: AddonPurchaseDialogProps) {
    const [billingCycle, setBillingCycle] = useState<'monthly' | 'yearly'>(
        subscription.billing_cycle || 'monthly'
    );
    const [isProcessing, setIsProcessing] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const price = billingCycle === 'monthly' ? addon.pricing.monthly : addon.pricing.yearly;
    const monthlyCost = billingCycle === 'monthly' ? price : Math.round(price / 12);
    const savings = billingCycle === 'yearly' ? Math.round((addon.pricing.monthly * 12 - addon.pricing.yearly) / addon.pricing.monthly * 100) : 0;

    const handleConfirm = async () => {
        setIsProcessing(true);
        setError(null);

        try {
            await onConfirm(addon.code, billingCycle);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al procesar la compra');
        } finally {
            setIsProcessing(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div className="max-w-lg w-full rounded-2xl bg-white shadow-xl overflow-hidden">
                {/* Header */}
                <div className="border-b border-slate-200 p-6">
                    <div className="flex items-start justify-between">
                        <div className="flex items-start gap-3">
                            <div className="rounded-lg bg-gradient-to-br from-purple-500 to-purple-600 p-2">
                                <Sparkles className="h-5 w-5 text-white" />
                            </div>
                            <div>
                                <h2 className="text-xl font-bold text-slate-900">{addon.name}</h2>
                                <p className="mt-1 text-sm text-slate-600">{addon.description}</p>
                            </div>
                        </div>
                        <button
                            onClick={onClose}
                            className="text-slate-400 hover:text-slate-600 transition"
                            disabled={isProcessing}
                        >
                            <X className="h-6 w-6" />
                        </button>
                    </div>
                </div>

                <div className="p-6 space-y-6">
                    {/* Error Display */}
                    {error && (
                        <div className="rounded-lg bg-red-50 border border-red-200 p-4 flex items-start gap-2">
                            <AlertCircle className="h-5 w-5 text-red-600 mt-0.5 flex-shrink-0" />
                            <p className="text-sm text-red-800">{error}</p>
                        </div>
                    )}

                    {/* Info Box */}
                    <div className="rounded-lg bg-blue-50 border border-blue-200 p-4">
                        <div className="flex items-start gap-2">
                            <CheckCircle className="h-5 w-5 text-blue-600 mt-0.5 flex-shrink-0" />
                            <div className="text-sm text-blue-900">
                                <p className="font-semibold">Activación inmediata</p>
                                <p className="mt-1">
                                    Este complemento se activará inmediatamente después de confirmar el pago.
                                    Podrás comenzar a usarlo de inmediato en tu cuenta.
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* Billing Cycle Selector */}
                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-3">
                            Ciclo de Facturación
                        </label>
                        <div className="grid grid-cols-2 gap-3">
                            {/* Monthly */}
                            <button
                                onClick={() => setBillingCycle('monthly')}
                                disabled={isProcessing}
                                className={`relative rounded-xl border-2 p-4 text-left transition ${
                                    billingCycle === 'monthly'
                                        ? 'border-slate-900 bg-slate-50'
                                        : 'border-slate-200 bg-white hover:border-slate-300'
                                } ${isProcessing ? 'opacity-50 cursor-not-allowed' : ''}`}
                            >
                                <div className="text-sm font-semibold text-slate-900">Mensual</div>
                                <div className="mt-1 text-2xl font-bold text-slate-900">
                                    {formatPrice(addon.pricing.monthly)}
                                </div>
                                <div className="text-xs text-slate-500">/mes</div>
                            </button>

                            {/* Yearly */}
                            <button
                                onClick={() => setBillingCycle('yearly')}
                                disabled={isProcessing}
                                className={`relative rounded-xl border-2 p-4 text-left transition ${
                                    billingCycle === 'yearly'
                                        ? 'border-slate-900 bg-slate-50'
                                        : 'border-slate-200 bg-white hover:border-slate-300'
                                } ${isProcessing ? 'opacity-50 cursor-not-allowed' : ''}`}
                            >
                                {savings > 0 && (
                                    <span className="absolute -top-2 -right-2 rounded-full bg-emerald-500 px-2 py-1 text-xs font-bold text-white">
                                        Ahorrá {savings}%
                                    </span>
                                )}
                                <div className="text-sm font-semibold text-slate-900">Anual</div>
                                <div className="mt-1 text-2xl font-bold text-slate-900">
                                    {formatPrice(monthlyCost)}
                                </div>
                                <div className="text-xs text-slate-500">/mes</div>
                                <div className="text-xs text-slate-400 mt-1">
                                    {formatPrice(addon.pricing.yearly)}/año
                                </div>
                            </button>
                        </div>
                    </div>

                    {/* Pricing Summary */}
                    <div className="rounded-lg bg-slate-50 border border-slate-200 p-4">
                        <div className="flex items-center justify-between text-sm">
                            <span className="text-slate-600">Costo del complemento:</span>
                            <span className="font-semibold text-slate-900">
                                {formatPrice(price)}
                                {billingCycle === 'monthly' ? '/mes' : '/año'}
                            </span>
                        </div>
                        {billingCycle === 'yearly' && (
                            <div className="mt-2 pt-2 border-t border-slate-300 flex items-center justify-between text-xs">
                                <span className="text-slate-500">Equivalente mensual:</span>
                                <span className="text-slate-700">{formatPrice(monthlyCost)}/mes</span>
                            </div>
                        )}
                    </div>

                    {/* Action Buttons */}
                    <div className="flex gap-3">
                        <Button
                            variant="outline"
                            onClick={onClose}
                            disabled={isProcessing}
                            className="flex-1"
                        >
                            Cancelar
                        </Button>
                        <Button
                            onClick={handleConfirm}
                            disabled={isProcessing}
                            className="flex-1 gap-2"
                        >
                            {isProcessing ? (
                                <>
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    Procesando...
                                </>
                            ) : (
                                <>
                                    <Sparkles className="h-4 w-4" />
                                    Confirmar y Pagar
                                </>
                            )}
                        </Button>
                    </div>

                    {/* Legal Notice */}
                    <p className="text-xs text-center text-slate-500">
                        Al confirmar, serás redirigido a MercadoPago para completar el pago de forma segura.
                        El complemento se activará automáticamente al confirmar el pago.
                    </p>
                </div>
            </div>
        </div>
    );
}
