'use client';

import { useState, useEffect } from 'react';
import { Loader2, AlertCircle, CheckCircle } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { previewSubscriptionChange } from '@/services/billing';
import type { CommercialSubscription, PreviewChangeResponse, PreviewChangeRequest } from '@/types/billing';

interface PlanChangeDialogProps {
    currentSubscription: CommercialSubscription;
    targetPlanCode: string;
    onClose: () => void;
    onConfirm: (preview: PreviewChangeResponse, config: PreviewChangeRequest) => void;
}

function formatPrice(cents: number): string {
    return `$${(cents / 100).toFixed(0)}`;
}

export function PlanChangeDialog({
    currentSubscription,
    targetPlanCode,
    onClose,
    onConfirm,
}: PlanChangeDialogProps) {
    const [preview, setPreview] = useState<PreviewChangeResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    
    // Customization state
    const [billingCycle, setBillingCycle] = useState<'monthly' | 'yearly'>(
        currentSubscription.billing_cycle || 'monthly'
    );
    const [enableCrm, setEnableCrm] = useState(false);
    const [enableInvoicing, setEnableInvoicing] = useState(false);
    const [branchesExtra, setBranchesExtra] = useState(currentSubscription.branches.extras_qty);
    const [seatsExtra, setSeatsExtra] = useState(currentSubscription.seats.extras_qty);

    // Load preview when configuration changes
    useEffect(() => {
        const loadPreview = async () => {
            setLoading(true);
            setError(null);

            try {
                const request: PreviewChangeRequest = {
                    plan_code: targetPlanCode,
                    billing_cycle: billingCycle,
                    crm: enableCrm,
                    invoicing: enableInvoicing,
                    branches_extra_qty: branchesExtra,
                    seats_extra_qty: seatsExtra,
                };

                const result = await previewSubscriptionChange(request);
                setPreview(result);
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Error al cargar preview');
            } finally {
                setLoading(false);
            }
        };

        loadPreview();
    }, [targetPlanCode, billingCycle, enableCrm, enableInvoicing, branchesExtra, seatsExtra]);

    const handleConfirm = () => {
        if (preview) {
            const config: PreviewChangeRequest = {
                plan_code: targetPlanCode,
                billing_cycle: billingCycle,
                crm: enableCrm,
                invoicing: enableInvoicing,
                branches_extra_qty: branchesExtra,
                seats_extra_qty: seatsExtra,
            };
            onConfirm(preview, config);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div className="max-w-2xl w-full max-h-[90vh] overflow-y-auto rounded-2xl bg-white shadow-xl">
                <div className="sticky top-0 bg-white border-b border-slate-200 p-6">
                    <div className="flex items-start justify-between">
                        <div>
                            <h2 className="text-2xl font-bold text-slate-900">Configurar Cambio de Plan</h2>
                            <p className="mt-1 text-sm text-slate-600">
                                Personalizá tu suscripción y revisá los costos antes de confirmar
                            </p>
                        </div>
                        <button
                            onClick={onClose}
                            className="text-slate-400 hover:text-slate-600"
                        >
                            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                </div>

                <div className="p-6 space-y-6">
                    {loading && (
                        <div className="flex items-center justify-center py-8">
                            <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
                        </div>
                    )}

                    {error && (
                        <div className="rounded-lg bg-red-50 border border-red-200 p-4 flex items-start gap-2">
                            <AlertCircle className="h-5 w-5 text-red-600 mt-0.5" />
                            <p className="text-sm text-red-800">{error}</p>
                        </div>
                    )}

                    {preview && (
                        <>
                            {/* Validation Errors */}
                            {preview.validation_errors.length > 0 && (
                                <div className="rounded-lg bg-red-50 border border-red-200 p-4">
                                    <div className="flex items-start gap-2">
                                        <AlertCircle className="h-5 w-5 text-red-600 mt-0.5" />
                                        <div className="text-sm text-red-800">
                                            <ul className="list-disc list-inside space-y-1">
                                                {preview.validation_errors.map((err, idx) => (
                                                    <li key={idx}>{err.message}</li>
                                                ))}
                                            </ul>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Change Summary */}
                            <div className="rounded-lg bg-blue-50 border border-blue-200 p-4">
                                <div className="flex items-start gap-2">
                                    {preview.is_upgrade ? (
                                        <CheckCircle className="h-5 w-5 text-blue-600 mt-0.5" />
                                    ) : (
                                        <AlertCircle className="h-5 w-5 text-amber-600 mt-0.5" />
                                    )}
                                    <div>
                                        <h3 className="font-semibold text-blue-900">{preview.change_summary}</h3>
                                        {preview.is_downgrade && (
                                            <p className="mt-1 text-sm text-blue-800">
                                                El cambio se aplicará al finalizar tu período de facturación actual.
                                            </p>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Billing Cycle */}
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-2">
                                    Ciclo de Facturación
                                </label>
                                <div className="flex gap-3">
                                    <button
                                        onClick={() => setBillingCycle('monthly')}
                                        className={`flex-1 rounded-lg border-2 p-3 text-sm font-medium transition ${
                                            billingCycle === 'monthly'
                                                ? 'border-slate-900 bg-slate-50'
                                                : 'border-slate-200 bg-white hover:border-slate-300'
                                        }`}
                                    >
                                        Mensual
                                    </button>
                                    <button
                                        onClick={() => setBillingCycle('yearly')}
                                        className={`flex-1 rounded-lg border-2 p-3 text-sm font-medium transition ${
                                            billingCycle === 'yearly'
                                                ? 'border-slate-900 bg-slate-50'
                                                : 'border-slate-200 bg-white hover:border-slate-300'
                                        }`}
                                    >
                                        Anual
                                        <Badge variant="secondary" className="ml-2 bg-green-100 text-green-700 text-xs">
                                            -20%
                                        </Badge>
                                    </button>
                                </div>
                            </div>

                            {/* Add-ons */}
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-2">
                                    Complementos (Add-ons)
                                </label>
                                <div className="space-y-2">
                                    <label className="flex items-center gap-3 rounded-lg border border-slate-200 p-3 hover:bg-slate-50 cursor-pointer">
                                        <input
                                            type="checkbox"
                                            checked={enableCrm}
                                            onChange={(e) => setEnableCrm(e.target.checked)}
                                            className="h-4 w-4 rounded border-slate-300"
                                        />
                                        <div className="flex-1">
                                            <div className="font-medium text-slate-900">CRM</div>
                                            <div className="text-xs text-slate-600">Gestión de clientes y ventas</div>
                                        </div>
                                        <div className="text-sm font-semibold text-slate-900">
                                            $20/mes
                                        </div>
                                    </label>
                                    <label className="flex items-center gap-3 rounded-lg border border-slate-200 p-3 hover:bg-slate-50 cursor-pointer">
                                        <input
                                            type="checkbox"
                                            checked={enableInvoicing}
                                            onChange={(e) => setEnableInvoicing(e.target.checked)}
                                            className="h-4 w-4 rounded border-slate-300"
                                        />
                                        <div className="flex-1">
                                            <div className="font-medium text-slate-900">Facturación</div>
                                            <div className="text-xs text-slate-600">Emisión de facturas electrónicas</div>
                                        </div>
                                        <div className="text-sm font-semibold text-slate-900">
                                            $150/mes
                                        </div>
                                    </label>
                                </div>
                            </div>

                            {/* Resources */}
                            <div className="grid gap-4 md:grid-cols-2">
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-2">
                                        Sucursales Extra
                                    </label>
                                    <div className="flex items-center gap-2">
                                        <button
                                            onClick={() => setBranchesExtra(Math.max(0, branchesExtra - 1))}
                                            className="rounded-lg border border-slate-300 px-3 py-2 hover:bg-slate-50"
                                        >
                                            -
                                        </button>
                                        <input
                                            type="number"
                                            value={branchesExtra}
                                            onChange={(e) => setBranchesExtra(Math.max(0, parseInt(e.target.value) || 0))}
                                            className="w-20 rounded-lg border border-slate-300 px-3 py-2 text-center"
                                            min="0"
                                        />
                                        <button
                                            onClick={() => setBranchesExtra(branchesExtra + 1)}
                                            className="rounded-lg border border-slate-300 px-3 py-2 hover:bg-slate-50"
                                        >
                                            +
                                        </button>
                                        <span className="text-sm text-slate-600">× $50/mes</span>
                                    </div>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-2">
                                        Usuarios Extra
                                    </label>
                                    <div className="flex items-center gap-2">
                                        <button
                                            onClick={() => setSeatsExtra(Math.max(0, seatsExtra - 1))}
                                            className="rounded-lg border border-slate-300 px-3 py-2 hover:bg-slate-50"
                                        >
                                            -
                                        </button>
                                        <input
                                            type="number"
                                            value={seatsExtra}
                                            onChange={(e) => setSeatsExtra(Math.max(0, parseInt(e.target.value) || 0))}
                                            className="w-20 rounded-lg border border-slate-300 px-3 py-2 text-center"
                                            min="0"
                                        />
                                        <button
                                            onClick={() => setSeatsExtra(seatsExtra + 1)}
                                            className="rounded-lg border border-slate-300 px-3 py-2 hover:bg-slate-50"
                                        >
                                            +
                                        </button>
                                        <span className="text-sm text-slate-600">× $5/mes</span>
                                    </div>
                                </div>
                            </div>

                            {/* Line Items */}
                            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                                <h3 className="font-semibold text-slate-900 mb-3">Detalle de Facturación</h3>
                                <div className="space-y-2">
                                    {preview.line_items.map((item, idx) => (
                                        <div key={idx} className="flex justify-between text-sm">
                                            <span className="text-slate-700">
                                                {item.description}
                                                {item.quantity > 1 && ` (×${item.quantity})`}
                                            </span>
                                            <span className="font-medium text-slate-900">
                                                {formatPrice(item.total)}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                                <div className="mt-4 pt-4 border-t border-slate-300">
                                    <div className="flex justify-between items-baseline">
                                        <span className="text-lg font-bold text-slate-900">Total</span>
                                        <div className="text-right">
                                            <div className="text-2xl font-bold text-slate-900">
                                                {formatPrice(preview.total_recurring)}
                                            </div>
                                            <div className="text-xs text-slate-600">
                                                {billingCycle === 'monthly' ? '/mes' : '/año'}
                                            </div>
                                        </div>
                                    </div>
                                    {preview.total_now !== preview.total_recurring && (
                                        <div className="mt-2 text-sm text-slate-600">
                                            Monto a pagar ahora: <span className="font-semibold">{formatPrice(preview.total_now)}</span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </>
                    )}
                </div>

                {/* Footer Actions */}
                <div className="sticky bottom-0 bg-white border-t border-slate-200 p-6">
                    <div className="flex gap-3 justify-end">
                        <Button variant="outline" onClick={onClose}>
                            Cancelar
                        </Button>
                        <Button
                            onClick={handleConfirm}
                            disabled={loading || !preview || preview.validation_errors.length > 0}
                        >
                            {preview?.requires_checkout ? 'Proceder al Pago' : 'Confirmar Cambio'}
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
}
