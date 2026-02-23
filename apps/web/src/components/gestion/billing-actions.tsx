'use client';

import { useState } from 'react';
import { Sparkles } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { PlanComparison } from '@/components/gestion/plan-comparison';
import { PlanChangeDialog } from '@/components/gestion/plan-change-dialog';
import { checkoutSubscriptionChange } from '@/services/billing';
import type { CommercialSubscription, PreviewChangeResponse, PreviewChangeRequest } from '@/types/billing';

interface BillingActionsProps {
    subscription: CommercialSubscription;
}

export function BillingActions({ subscription }: BillingActionsProps) {
    const [showComparison, setShowComparison] = useState(false);
    const [selectedPlan, setSelectedPlan] = useState<string | null>(null);
    const [isProcessing, setIsProcessing] = useState(false);

    const handleSelectPlan = (planCode: string) => {
        setSelectedPlan(planCode);
        setShowComparison(false);
    };

    const handleConfirmChange = async (preview: PreviewChangeResponse, config: PreviewChangeRequest) => {
        setIsProcessing(true);
        
        try {
            // Use the config provided by PlanChangeDialog
            const result = await checkoutSubscriptionChange(config);
            
            if (result.requires_payment && result.checkout_url) {
                // Redirect to MercadoPago
                window.location.href = result.checkout_url;
            } else if (result.applied) {
                // Change applied immediately
                alert(`✅ ${result.message}\n\nLos cambios se aplicaron correctamente.`);
                window.location.reload();
            } else if (result.scheduled) {
                // Downgrade scheduled
                alert(`📅 ${result.message}\n\nLos cambios se aplicarán en tu próximo ciclo de facturación.`);
                setSelectedPlan(null);
            }
        } catch (error) {
            console.error('Checkout error:', error);
            alert('Error al procesar el cambio. Por favor intentá nuevamente.');
        } finally {
            setIsProcessing(false);
        }
    };

    if (!subscription.can_manage) {
        return null;
    }

    return (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6">
            {!showComparison ? (
                <div className="text-center space-y-2">
                    <h3 className="text-lg font-semibold text-slate-900">¿Querés cambiar de plan o agregar complementos?</h3>
                    <p className="text-sm text-slate-600">
                        Explorá nuestros planes, compará características y personalizá tu suscripción.
                    </p>
                    <Button
                        onClick={() => setShowComparison(true)}
                        className="mt-4 gap-2"
                        disabled={isProcessing}
                    >
                        <Sparkles className="h-4 w-4" />
                        Gestionar Plan
                    </Button>
                </div>
            ) : (
                <>
                    <div className="mb-4">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setShowComparison(false)}
                            disabled={isProcessing}
                        >
                            ← Volver a resumen
                        </Button>
                    </div>
                    <PlanComparison
                        currentSubscription={subscription}
                        onSelectPlan={handleSelectPlan}
                    />
                </>
            )}

            {selectedPlan && !isProcessing && (
                <PlanChangeDialog
                    currentSubscription={subscription}
                    targetPlanCode={selectedPlan}
                    onClose={() => setSelectedPlan(null)}
                    onConfirm={handleConfirmChange}
                />
            )}
        </div>
    );
}
