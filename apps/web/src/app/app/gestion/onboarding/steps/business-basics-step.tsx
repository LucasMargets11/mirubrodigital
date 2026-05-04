'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { useSubmitBusinessBasics, useSkipOnboardingStep } from '@/features/onboarding/gestion/hooks';
import type { GestionOnboardingContext } from '@/features/onboarding/gestion/types';

interface Props {
    context: GestionOnboardingContext;
    onComplete: () => void;
    onSkip: () => void;
}

export function BusinessBasicsStep({ context, onComplete, onSkip }: Props) {
    const submitMutation = useSubmitBusinessBasics();
    const skipMutation = useSkipOnboardingStep();

    const [businessName, setBusinessName] = useState(
        context.business_basics.trade_name || context.business_basics.name || '',
    );
    const [phone, setPhone] = useState(context.business_basics.phone || '');
    const [email, setEmail] = useState(context.business_basics.email || '');
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        const trimmedName = businessName.trim();
        if (trimmedName.length < 2) {
            setError('El nombre del negocio debe tener al menos 2 caracteres.');
            return;
        }
        if (trimmedName.length > 120) {
            setError('El nombre del negocio no puede superar los 120 caracteres.');
            return;
        }

        try {
            await submitMutation.mutateAsync({
                business_name: trimmedName,
                phone: phone.trim() || null,
                email: email.trim() || null,
            });
            onComplete();
        } catch {
            setError('No se pudieron guardar los datos. Intentá nuevamente.');
        }
    };

    const handleSkip = async () => {
        try {
            await skipMutation.mutateAsync({ step_id: 'business_basics' });
        } catch {
            // non-fatal: just advance
        }
        onSkip();
    };

    const isSubmitting = submitMutation.isPending;
    const isSkipping = skipMutation.isPending;

    return (
        <form onSubmit={handleSubmit} className="space-y-6">
            {/* Step header */}
            <div className="space-y-1">
                <h2 className="text-lg font-semibold text-slate-900">
                    ¿Con qué nombre conocen a tu negocio?
                </h2>
                <p className="text-sm text-slate-500">
                    Este nombre aparece en los recibos y documentos que le mandás a tus clientes.
                </p>
            </div>

            {/* Fields */}
            <div className="space-y-4">
                <div className="space-y-1.5">
                    <label htmlFor="business-name" className="block text-sm font-medium text-slate-700">
                        Nombre del negocio <span className="text-red-500">*</span>
                    </label>
                    <input
                        id="business-name"
                        type="text"
                        autoFocus
                        placeholder="Ej: La Panadería de José"
                        value={businessName}
                        onChange={(e) => setBusinessName(e.target.value)}
                        maxLength={120}
                        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                        <label htmlFor="phone" className="block text-sm font-medium text-slate-700">
                            Teléfono
                        </label>
                        <input
                            id="phone"
                            type="tel"
                            placeholder="Ej: +54 9 11 1234-5678"
                            value={phone}
                            onChange={(e) => setPhone(e.target.value)}
                            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                        />
                    </div>

                    <div className="space-y-1.5">
                        <label htmlFor="email" className="block text-sm font-medium text-slate-700">
                            Email
                        </label>
                        <input
                            id="email"
                            type="email"
                            placeholder="Ej: info@minegocio.com"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                        />
                    </div>
                </div>
            </div>

            {/* Error */}
            {error && (
                <p className="text-sm text-red-600">{error}</p>
            )}

            {/* Actions */}
            <div className="flex items-center justify-between">
                <button
                    type="button"
                    onClick={handleSkip}
                    disabled={isSkipping || isSubmitting}
                    className="text-sm text-slate-400 hover:text-slate-600 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                >
                    {isSkipping ? 'Saltando...' : 'Saltar este paso'}
                </button>

                <Button type="submit" disabled={isSubmitting || isSkipping}>
                    {isSubmitting ? 'Guardando...' : 'Guardar y continuar'}
                </Button>
            </div>
        </form>
    );
}
