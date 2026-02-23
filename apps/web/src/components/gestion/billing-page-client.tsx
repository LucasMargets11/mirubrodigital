'use client';

import { useState } from 'react';
import { Plus } from 'lucide-react';

import type { CommercialSubscription } from '@/types/billing';
import { BillingActions } from '@/components/gestion/billing-actions';
import { AddonPurchaseDialog } from '@/components/gestion/addon-purchase-dialog';
import { checkoutAddonPurchase } from '@/services/billing';
import { Button } from '@/components/ui/button';

function formatPrice(cents: number): string {
    return `$${(cents / 100).toFixed(0)}`;
}

interface BillingPageClientProps {
    subscription: CommercialSubscription;
}

export function BillingPageClient({ subscription }: BillingPageClientProps) {
    const [selectedAddon, setSelectedAddon] = useState<string | null>(null);

    const addon = selectedAddon 
        ? [...subscription.addons.available, ...subscription.addons.active].find(a => a.code === selectedAddon)
        : null;

    const handleAddonPurchase = async (addonCode: string, billingCycle: 'monthly' | 'yearly') => {
        try {
            const result = await checkoutAddonPurchase({
                addon_code: addonCode,
                billing_cycle: billingCycle,
            });
            
            if (result.checkout_url) {
                // Redirect to MercadoPago
                window.location.href = result.checkout_url;
            } else {
                // Should not happen, but handle gracefully
                alert('Error: No se generó el link de pago');
                setSelectedAddon(null);
            }
        } catch (error) {
            console.error('Addon purchase error:', error);
            throw error; // Let the dialog handle the error
        }
    };

    const { current_plan, billing_cycle, branches, seats, addons, can_manage } = subscription;
    const pricePerMonth = billing_cycle === 'monthly' ? current_plan.pricing.monthly : current_plan.pricing.yearly / 12;

    return (
        <section className="space-y-6">
            <header>
                <p className="text-xs uppercase tracking-wide text-slate-400">Gestión Comercial</p>
                <h1 className="text-3xl font-semibold text-slate-900">Plan y Facturación</h1>
                <p className="text-sm text-slate-500">
                    Administrá tu plan, sucursales y complementos.
                </p>
            </header>

            {/* Current Plan Card */}
            <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="space-y-4">
                    <div className="flex items-start justify-between">
                        <div>
                            <div className="flex items-center gap-3">
                                <h2 className="text-2xl font-semibold text-slate-900">{current_plan.name}</h2>
                                {current_plan.is_custom && (
                                    <span className="rounded-full bg-purple-100 px-3 py-1 text-xs font-semibold text-purple-700">
                                        Personalizado
                                    </span>
                                )}
                            </div>
                            <p className="mt-1 text-sm text-slate-500">{current_plan.description}</p>
                        </div>
                        <div className="text-right">
                            <p className="text-3xl font-bold text-slate-900">{formatPrice(pricePerMonth)}</p>
                            <p className="text-xs text-slate-500">
                                {billing_cycle === 'monthly' ? '/mes' : '/mes (facturado anualmente)'}
                            </p>
                        </div>
                    </div>

                    <div className="flex flex-wrap gap-2">
                        {current_plan.features.map((feature) => (
                            <span key={feature} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                                {feature}
                            </span>
                        ))}
                    </div>

                    {!can_manage && (
                        <div className="rounded-lg bg-amber-50 border border-amber-200 p-3">
                            <p className="text-xs text-amber-800">
                                Solo el propietario de la cuenta puede gestionar el plan y facturación.
                            </p>
                        </div>
                    )}
                </div>
            </article>

            {/* Resources Grid */}
            <div className="grid gap-4 md:grid-cols-2">
                {/* Branches Card */}
                <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <h3 className="text-lg font-semibold text-slate-900">Sucursales</h3>
                    <div className="mt-4 space-y-3">
                        <div className="flex items-baseline gap-2">
                            <span className="text-3xl font-bold text-slate-900">{branches.used}</span>
                            <span className="text-sm text-slate-500">
                                / {branches.max_total === null ? '∞' : branches.max_total} {branches.max_total === 1 ? 'sucursal' : 'sucursales'}
                            </span>
                        </div>
                        <div className="space-y-1 text-sm">
                            <p className="text-slate-600">
                                <span className="font-medium">{branches.included}</span> incluidas en tu plan
                            </p>
                            {branches.extras_qty > 0 && (
                                <p className="text-slate-600">
                                    <span className="font-medium">{branches.extras_qty}</span> extras contratadas 
                                    ({formatPrice(branches.unit_pricing.monthly)}/mes c/u)
                                </p>
                            )}
                            {branches.can_add_more && branches.remaining !== null && branches.remaining > 0 && (
                                <p className="text-emerald-600">
                                    Podés agregar hasta <span className="font-medium">{branches.remaining}</span> más
                                </p>
                            )}
                            {!branches.can_add_more && branches.max_total !== null && (
                                <p className="text-amber-600">
                                    Límite alcanzado para tu plan
                                </p>
                            )}
                        </div>
                    </div>
                </article>

                {/* Seats Card */}
                <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <h3 className="text-lg font-semibold text-slate-900">Usuarios</h3>
                    <div className="mt-4 space-y-3">
                        <div className="flex items-baseline gap-2">
                            <span className="text-3xl font-bold text-slate-900">{seats.total}</span>
                            <span className="text-sm text-slate-500">usuarios totales</span>
                        </div>
                        <div className="space-y-1 text-sm">
                            <p className="text-slate-600">
                                <span className="font-medium">{seats.included}</span> incluidos en tu plan
                            </p>
                            {seats.extras_qty > 0 && (
                                <p className="text-slate-600">
                                    <span className="font-medium">{seats.extras_qty}</span> extras contratados
                                    ({formatPrice(seats.unit_pricing.monthly)}/mes c/u)
                                </p>
                            )}
                        </div>
                    </div>
                </article>
            </div>

            {/* Addons Section */}
            <div className="space-y-3">
                <h3 className="text-lg font-semibold text-slate-900">Complementos</h3>
                
                {(addons.active.length > 0 || addons.included.length > 0 || addons.available.length > 0) ? (
                    <div className="grid gap-4 md:grid-cols-2">
                        {/* Active Addons */}
                        {addons.active.map((addon) => (
                            <article key={addon.code} className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 shadow-sm">
                                <div className="space-y-3">
                                    <div className="flex items-start justify-between">
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2">
                                                <h4 className="font-semibold text-slate-900">{addon.name}</h4>
                                                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                                                    Activo
                                                </span>
                                            </div>
                                            <p className="mt-1 text-xs text-slate-600">{addon.description}</p>
                                        </div>
                                        <p className="text-sm font-semibold text-slate-900">
                                            {formatPrice(addon.pricing.monthly)}/mes
                                        </p>
                                    </div>
                                    {can_manage && (
                                        <div className="pt-2 border-t border-emerald-200">
                                            <p className="text-xs text-emerald-700">
                                                ✓ Activo en tu suscripción
                                            </p>
                                        </div>
                                    )}
                                </div>
                            </article>
                        ))}

                        {/* Included Addons */}
                        {addons.included.map((addon) => (
                            <article key={addon.code} className="rounded-2xl border border-blue-200 bg-blue-50 p-4 shadow-sm">
                                <div className="space-y-3">
                                    <div className="flex items-start justify-between">
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2">
                                                <h4 className="font-semibold text-slate-900">{addon.name}</h4>
                                                <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-700">
                                                    Incluido
                                                </span>
                                            </div>
                                            <p className="mt-1 text-xs text-slate-600">{addon.description}</p>
                                        </div>
                                        <p className="text-sm font-semibold text-slate-500">Sin cargo</p>
                                    </div>
                                    <div className="pt-2 border-t border-blue-200">
                                        <p className="text-xs text-blue-700">
                                            ✓ Incluido en tu plan {current_plan.name}
                                        </p>
                                    </div>
                                </div>
                            </article>
                        ))}

                        {/* Available Addons */}
                        {addons.available.map((addon) => (
                            <article key={addon.code} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm hover:shadow-md transition">
                                <div className="space-y-3">
                                    <div className="flex items-start justify-between">
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2">
                                                <h4 className="font-semibold text-slate-900">{addon.name}</h4>
                                                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
                                                    Disponible
                                                </span>
                                            </div>
                                            <p className="mt-1 text-xs text-slate-600">{addon.description}</p>
                                            <p className="mt-2 text-sm font-semibold text-slate-900">
                                                Desde {formatPrice(addon.pricing.monthly)}/mes
                                            </p>
                                        </div>
                                    </div>
                                    {can_manage && (
                                        <div className="pt-2 border-t border-slate-200">
                                            <Button
                                                size="sm"
                                                onClick={() => setSelectedAddon(addon.code)}
                                                className="w-full gap-2"
                                            >
                                                <Plus className="h-4 w-4" />
                                                Agregar a mi Plan
                                            </Button>
                                        </div>
                                    )}
                                </div>
                            </article>
                        ))}
                    </div>
                ) : (
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6 text-center">
                        <p className="text-sm text-slate-600">
                            Tu plan {current_plan.name} incluye todos los módulos disponibles.
                        </p>
                    </div>
                )}
            </div>

            {/* Addon Purchase Dialog */}
            {selectedAddon && addon && (
                <AddonPurchaseDialog
                    addon={addon}
                    subscription={subscription}
                    onClose={() => setSelectedAddon(null)}
                    onConfirm={handleAddonPurchase}
                />
            )}

            {/* Action Section */}
            <BillingActions subscription={subscription} />
        </section>
    );
}
