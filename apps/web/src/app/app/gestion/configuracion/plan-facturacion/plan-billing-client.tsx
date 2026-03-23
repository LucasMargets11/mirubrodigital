'use client';

import { useRef, useState, useEffect } from 'react';

import { ToastBubble } from '@/components/app/toast';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Modal } from '@/components/ui/modal';
import {
    useSubscriptionStatusQuery,
    useCancelSubscriptionMutation,
    useUndoCancelSubscriptionMutation,
} from '@/features/billing/subscription-hooks';
import type { SubscriptionInfo } from '@/features/billing/subscription-types';
import type { Session } from '@/lib/auth';
import { cn } from '@/lib/utils';

type ToastState = { message: string; tone: 'success' | 'error' };

function formatDate(isoString: string | null): string {
    if (!isoString) return '—';
    try {
        return new Date(isoString).toLocaleDateString('es-AR', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
        });
    } catch {
        return isoString;
    }
}

function statusBadge(sub: SubscriptionInfo) {
    if (sub.cancel_at_period_end) {
        return <Badge className="bg-amber-100 text-amber-800 border-amber-200">Baja programada</Badge>;
    }
    const map: Record<string, { label: string; className: string }> = {
        active: { label: 'Activo', className: 'bg-emerald-100 text-emerald-800 border-emerald-200' },
        trialing: { label: 'Período de prueba', className: 'bg-blue-100 text-blue-800 border-blue-200' },
        past_due: { label: 'Pago vencido', className: 'bg-orange-100 text-orange-800 border-orange-200' },
        suspended: { label: 'Suspendido', className: 'bg-red-100 text-red-800 border-red-200' },
        canceled: { label: 'Cancelado', className: 'bg-slate-100 text-slate-600 border-slate-200' },
        checkout_pending: { label: 'Pendiente', className: 'bg-slate-100 text-slate-600 border-slate-200' },
    };
    const info = map[sub.status] ?? { label: sub.status_display, className: '' };
    return <Badge className={info.className}>{info.label}</Badge>;
}

type PlanBillingClientProps = {
    session: Session;
};

export function PlanBillingClient({ session }: PlanBillingClientProps) {
    const statusQuery = useSubscriptionStatusQuery();
    const cancelMutation = useCancelSubscriptionMutation();
    const undoCancelMutation = useUndoCancelSubscriptionMutation();

    const [showCancelModal, setShowCancelModal] = useState(false);
    const [toast, setToast] = useState<ToastState | null>(null);
    const toastTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const isOwner = session.current.role === 'owner';

    useEffect(() => {
        return () => {
            if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
        };
    }, []);

    const showToast = (message: string, tone: 'success' | 'error' = 'success') => {
        if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
        setToast({ message, tone });
        toastTimeoutRef.current = setTimeout(() => setToast(null), 3000);
    };

    const handleConfirmCancel = async () => {
        try {
            await cancelMutation.mutateAsync('');
            setShowCancelModal(false);
            showToast('Baja programada correctamente.');
        } catch (error) {
            const detail = (error as { payload?: { detail?: string } })?.payload?.detail;
            showToast(detail || 'No pudimos programar la baja. Intentá de nuevo.', 'error');
        }
    };

    const handleUndoCancel = async () => {
        try {
            await undoCancelMutation.mutateAsync();
            showToast('La baja fue revertida exitosamente.');
        } catch (error) {
            const detail = (error as { payload?: { detail?: string } })?.payload?.detail;
            showToast(detail || 'No pudimos deshacer la baja. Intentá de nuevo.', 'error');
        }
    };

    // Loading state
    if (statusQuery.isLoading) {
        return (
            <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
                <div className="mb-8">
                    <h1 className="text-3xl font-bold tracking-tight text-slate-900">Plan y Facturación</h1>
                    <p className="mt-2 text-sm text-slate-600">Administrá tu suscripción y datos de facturación.</p>
                </div>
                <Card>
                    <CardContent className="py-12">
                        <div className="flex items-center justify-center gap-3 text-slate-500">
                            <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
                            <span className="text-sm">Cargando información del plan…</span>
                        </div>
                    </CardContent>
                </Card>
            </div>
        );
    }

    // Error state
    if (statusQuery.isError) {
        return (
            <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
                <div className="mb-8">
                    <h1 className="text-3xl font-bold tracking-tight text-slate-900">Plan y Facturación</h1>
                    <p className="mt-2 text-sm text-slate-600">Administrá tu suscripción y datos de facturación.</p>
                </div>
                <Card>
                    <CardContent className="py-12">
                        <p className="text-center text-sm text-rose-600">
                            No pudimos cargar la información del plan. Intentá recargando la página.
                        </p>
                    </CardContent>
                </Card>
            </div>
        );
    }

    const data = statusQuery.data;
    const sub = data?.subscription;

    // Empty state — no subscription
    if (!data?.has_subscription || !sub) {
        return (
            <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
                <div className="mb-8">
                    <h1 className="text-3xl font-bold tracking-tight text-slate-900">Plan y Facturación</h1>
                    <p className="mt-2 text-sm text-slate-600">Administrá tu suscripción y datos de facturación.</p>
                </div>
                <Card>
                    <CardContent className="py-12">
                        <p className="text-center text-sm text-slate-500">
                            No tenés una suscripción activa en este momento.
                        </p>
                    </CardContent>
                </Card>
            </div>
        );
    }

    const canCancel =
        isOwner &&
        sub.can_manage_cancellation &&
        !sub.cancel_at_period_end &&
        sub.status !== 'canceled' &&
        sub.status !== 'checkout_pending' &&
        sub.status !== 'suspended';

    const canUndoCancel =
        isOwner &&
        sub.can_manage_cancellation &&
        sub.cancel_at_period_end &&
        sub.status !== 'canceled';

    const renewalLabel = sub.cancel_at_period_end
        ? 'Acceso hasta'
        : 'Próxima renovación';

    return (
        <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
            <div className="mb-8">
                <h1 className="text-3xl font-bold tracking-tight text-slate-900">Plan y Facturación</h1>
                <p className="mt-2 text-sm text-slate-600">Administrá tu suscripción y datos de facturación.</p>
            </div>

            {/* Plan info card */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <CardTitle className="text-lg">Tu plan actual</CardTitle>
                        {statusBadge(sub)}
                    </div>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid gap-4 sm:grid-cols-2">
                        <div>
                            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Plan</p>
                            <p className="mt-1 text-base font-semibold text-slate-900">{sub.plan_name}</p>
                        </div>
                        {sub.current_period_end && (
                            <div>
                                <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{renewalLabel}</p>
                                <p className="mt-1 text-base font-semibold text-slate-900">
                                    {formatDate(sub.current_period_end)}
                                </p>
                            </div>
                        )}
                    </div>

                    {(sub.max_seats != null || sub.max_branches != null) && (
                        <div>
                            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Límites del plan</p>
                            <p className="mt-1 text-base font-semibold text-slate-900">
                                {sub.max_seats != null && `${sub.max_seats} usuario${sub.max_seats !== 1 ? 's' : ''}`}
                                {sub.max_seats != null && sub.max_branches != null && ' · '}
                                {sub.max_branches != null && `${sub.max_branches} sucursal${sub.max_branches !== 1 ? 'es' : ''}`}
                            </p>
                        </div>
                    )}

                    {/* Cancellation scheduled banner */}
                    {sub.cancel_at_period_end && sub.status !== 'canceled' && (
                        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                            <p className="text-sm font-semibold text-amber-800">
                                Baja programada para el {formatDate(sub.cancel_effective_at)}
                            </p>
                            <p className="mt-1 text-sm text-amber-700">
                                Vas a conservar el acceso hasta esa fecha. Después, tu plan se dará de baja y no se renovará automáticamente.
                            </p>
                        </div>
                    )}

                    {/* Canceled banner */}
                    {sub.status === 'canceled' && (
                        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                            <p className="text-sm font-semibold text-slate-700">
                                Tu suscripción fue cancelada el {formatDate(sub.canceled_at)}.
                            </p>
                        </div>
                    )}

                    {/* Actions */}
                    <div className="flex items-center gap-3 pt-2">
                        {canCancel && (
                            <button
                                type="button"
                                onClick={() => setShowCancelModal(true)}
                                className="rounded-lg border border-rose-200 bg-white px-4 py-2 text-sm font-medium text-rose-600 transition hover:bg-rose-50 disabled:opacity-50"
                                disabled={cancelMutation.isPending}
                            >
                                Cancelar suscripción
                            </button>
                        )}

                        {canUndoCancel && (
                            <button
                                type="button"
                                onClick={handleUndoCancel}
                                className="rounded-lg border border-emerald-200 bg-white px-4 py-2 text-sm font-medium text-emerald-700 transition hover:bg-emerald-50 disabled:opacity-50"
                                disabled={undoCancelMutation.isPending}
                            >
                                {undoCancelMutation.isPending ? 'Revirtiendo…' : 'Deshacer baja'}
                            </button>
                        )}

                        {!isOwner && (
                            <p className="text-xs text-slate-400">
                                Solo el propietario de la cuenta puede gestionar la suscripción.
                            </p>
                        )}
                    </div>
                </CardContent>
            </Card>

            {/* Cancel confirmation modal */}
            <Modal
                open={showCancelModal}
                title="¿Querés cancelar tu suscripción?"
                onClose={() => setShowCancelModal(false)}
            >
                <p className="text-sm text-slate-700">
                    Vas a seguir teniendo acceso hasta el{' '}
                    <span className="font-semibold">{formatDate(sub.current_period_end)}</span>.
                </p>
                <p className="text-sm text-slate-500">
                    Después de esa fecha, tu plan se dará de baja y no se renovará automáticamente.
                </p>
                <div className="mt-6 flex items-center justify-end gap-3">
                    <button
                        type="button"
                        onClick={() => setShowCancelModal(false)}
                        className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100"
                        disabled={cancelMutation.isPending}
                    >
                        Volver
                    </button>
                    <button
                        type="button"
                        onClick={handleConfirmCancel}
                        className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-rose-700 disabled:opacity-50"
                        disabled={cancelMutation.isPending}
                    >
                        {cancelMutation.isPending ? 'Procesando…' : 'Confirmar cancelación'}
                    </button>
                </div>
            </Modal>

            {toast && <ToastBubble message={toast.message} tone={toast.tone} />}
        </div>
    );
}
