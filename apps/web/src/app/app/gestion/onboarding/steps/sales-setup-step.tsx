'use client';

import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { useSubmitSalesSetup } from '@/features/onboarding/gestion/hooks';
import type { GestionOnboardingContext } from '@/features/onboarding/gestion/types';

interface Props {
    context: GestionOnboardingContext;
    onComplete: () => void;
    onBack: () => void;
    isCompleting?: boolean;
}

const STARTER_PLANS = new Set(['starter', 'start']);

export function SalesSetupStep({ context, onComplete, onBack, isCompleting = false }: Props) {
    const setupMutation = useSubmitSalesSetup();
    const isStarter = STARTER_PLANS.has(context.plan.code);
    // Prevents green checkmark from flashing before the API call starts
    const [hasStarted, setHasStarted] = useState(false);

    // Auto-apply on mount — no user input required
    useEffect(() => {
        setHasStarted(true);
        setupMutation.mutate(undefined, {
            onSuccess: () => {
                // noop — user clicks "Siguiente" explicitly
            },
        });
        // Run once only
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleContinue = () => {
        onComplete();
    };

    return (
        <div className="space-y-6">
            {/* Step header */}
            <div className="space-y-1">
                <h2 className="text-lg font-semibold text-slate-900">
                    Listo para vender
                </h2>
                <p className="text-sm text-slate-500">
                    {isStarter
                        ? 'Ya configuramos tu cuenta para que puedas registrar ventas sin trámites adicionales.'
                        : 'Tu plan incluye opciones avanzadas de configuración de caja. Podés ajustarlas desde Configuración cuando quieras.'}
                </p>
            </div>

            {/* Status indicator */}
            <div className="flex items-start gap-3 rounded-lg bg-emerald-50 p-4">
                {!hasStarted || setupMutation.isPending ? (
                    <div className="mt-0.5 h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-emerald-400 border-t-transparent" />
                ) : (
                    <svg className="mt-0.5 h-5 w-5 shrink-0 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                )}
                <div>
                    <p className="text-sm font-medium text-emerald-800">
                        {!hasStarted || setupMutation.isPending ? 'Configurando...' : 'Configuración aplicada'}
                    </p>
                    {isStarter && hasStarted && !setupMutation.isPending && (
                        <p className="mt-0.5 text-xs text-emerald-700">
                            Podés registrar ventas directamente sin necesidad de abrir una sesión de caja.
                        </p>
                    )}
                </div>
            </div>

            {setupMutation.isError && (
                <p className="text-sm text-red-600">
                    Hubo un problema al configurar las ventas, pero podés continuar. Podés ajustar esto luego desde Configuración.
                </p>
            )}

            {setupMutation.data?.warning && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                    <p className="text-sm text-amber-800">
                        {setupMutation.data.warning}
                    </p>
                </div>
            )}

            {/* Actions */}
            <div className="flex items-center justify-between">
                <button
                    type="button"
                    onClick={onBack}
                    disabled={!hasStarted || setupMutation.isPending || isCompleting}
                    className="text-sm text-slate-400 hover:text-slate-600 disabled:opacity-50"
                >
                    ← Volver
                </button>

                <Button
                    type="button"
                    onClick={handleContinue}
                    disabled={!hasStarted || setupMutation.isPending || isCompleting}
                >
                    {isCompleting
                        ? 'Finalizando...'
                        : (!hasStarted || setupMutation.isPending ? 'Configurando...' : 'Siguiente →')}
                </Button>
            </div>
        </div>
    );
}
