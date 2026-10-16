'use client';

import { useCallback, useEffect, useState } from 'react';

import { disconnectMercadoPago, getMercadoPagoConnectionStatus, startMercadoPagoOAuth } from './api';
import type { MercadoPagoConnectionStatus, MercadoPagoOAuthContext } from './types';

export type MercadoPagoReturn = 'connected' | 'error' | null;

type Props = {
    /** Producto que inicia el OAuth; el backend decide a qué pantalla volver. */
    context: MercadoPagoOAuthContext;
    /** Roles con `manage_settings` pueden ver el estado de la conexión. */
    canView: boolean;
    /** Conectar/reconectar/desconectar: solo OWNER/ADMIN (acción financiera). */
    canManage: boolean;
    /** Resultado del callback OAuth (`?mp=connected|error`). */
    mpReturn?: MercadoPagoReturn;
    description?: string;
    /** Inyectable para tests; por defecto navega a Mercado Pago. */
    navigate?: (url: string) => void;
};

type View = 'loading' | 'load_error' | 'not_connected' | 'connected' | 'reconnect';

function viewFor(status: MercadoPagoConnectionStatus): View {
    if (status.connected) return 'connected';
    // Existe una conexión pero ya no sirve para cobrar (expired/revoked/error).
    if (status.status) return 'reconnect';
    return 'not_connected';
}

function clearReturnParam() {
    if (typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    if (!url.searchParams.has('mp')) return;
    url.searchParams.delete('mp');
    window.history.replaceState(window.history.state, '', url.toString());
}

/**
 * Conexión de la cuenta Mercado Pago del Business (`apps.merchant_payments`).
 * Muestra solo estado e identificación pública mínima; nunca tokens ni detalles técnicos.
 */
export function MercadoPagoConnectionCard({
    context,
    canView,
    canManage,
    mpReturn = null,
    description = 'Conectá tu cuenta para recibir las señas de tus reservas directamente.',
    navigate = (url) => window.location.assign(url),
}: Props) {
    const [status, setStatus] = useState<MercadoPagoConnectionStatus | null>(null);
    const [view, setView] = useState<View>('loading');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(canView && mpReturn === 'error' ? 'No pudimos conectar Mercado Pago. Probá de nuevo.' : '');
    const [notice, setNotice] = useState(canView && mpReturn === 'connected' ? 'Mercado Pago quedó conectado.' : '');

    const applyStatus = useCallback((next: MercadoPagoConnectionStatus | null): View => {
        const nextView = next ? viewFor(next) : 'load_error';
        setStatus(next);
        setView(nextView);
        return nextView;
    }, []);

    const refresh = useCallback(
        () => getMercadoPagoConnectionStatus().then(applyStatus, () => applyStatus(null)),
        [applyStatus],
    );

    useEffect(() => {
        if (!canView) return;
        clearReturnParam();
        // Siempre se consulta el estado real al montar (incluido el retorno del
        // callback): el aviso de éxito solo queda si el backend lo confirma.
        let active = true;
        getMercadoPagoConnectionStatus()
            .catch(() => null)
            .then((next) => {
                if (!active) return;
                if (applyStatus(next) !== 'connected' && mpReturn === 'connected') setNotice('');
            });
        return () => {
            active = false;
        };
    }, [canView, mpReturn, applyStatus]);

    async function handleConnect() {
        if (!canManage) return;
        setBusy(true);
        setError('');
        setNotice('');
        try {
            const { auth_url } = await startMercadoPagoOAuth(context);
            navigate(auth_url);
        } catch {
            setError('No pudimos iniciar la conexión con Mercado Pago. Probá de nuevo.');
            setBusy(false);
        }
    }

    async function handleDisconnect() {
        if (!canManage) return;
        if (!window.confirm('¿Desconectar Mercado Pago? Dejarás de poder cobrar online hasta que lo vuelvas a conectar.')) {
            return;
        }
        setBusy(true);
        setError('');
        setNotice('');
        try {
            await disconnectMercadoPago();
            setNotice('Mercado Pago quedó desconectado.');
        } catch {
            setError('No pudimos desconectar Mercado Pago. Probá de nuevo.');
        } finally {
            await refresh();
            setBusy(false);
        }
    }

    return (
        <section className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" aria-label="Mercado Pago">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h2 className="text-sm font-semibold text-slate-800">Mercado Pago</h2>
                    <p className="text-xs text-slate-500">{description}</p>
                </div>
                {canView && view === 'connected' && (
                    <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-green-200 bg-green-50 px-2.5 py-0.5 text-xs font-medium text-green-700">
                        <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                        Conectado
                    </span>
                )}
                {canView && (view === 'not_connected' || view === 'reconnect') && (
                    <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700">
                        <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                        No conectado
                    </span>
                )}
            </div>

            {!canView && (
                <p className="text-sm text-slate-500">
                    Solo los administradores del negocio pueden conectar o desconectar Mercado Pago.
                </p>
            )}

            {canView && !canManage && view !== 'loading' && view !== 'load_error' && (
                <p className="text-sm text-slate-500">
                    Solo el dueño o un administrador del negocio puede conectar o desconectar Mercado Pago.
                </p>
            )}

            {canView && view === 'loading' && <p className="text-sm text-slate-500">Consultando estado…</p>}

            {canView && view === 'load_error' && (
                <div className="space-y-2">
                    <p className="text-sm text-slate-600">No pudimos consultar el estado de Mercado Pago.</p>
                    <button
                        type="button"
                        onClick={() => void refresh()}
                        className="rounded-full border border-slate-300 px-4 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                    >
                        Reintentar
                    </button>
                </div>
            )}

            {canView && view === 'not_connected' && (
                <div className="space-y-3">
                    <p className="text-sm text-slate-600">Conectá Mercado Pago para cobrar señas online.</p>
                    {canManage && <button
                        type="button"
                        onClick={handleConnect}
                        disabled={busy}
                        className="rounded-full bg-[#009ee3] px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#007ab8] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        Conectar Mercado Pago
                    </button>}
                </div>
            )}

            {canView && view === 'reconnect' && (
                <div className="space-y-3">
                    <p className="text-sm text-slate-600">Necesitamos que vuelvas a conectar Mercado Pago.</p>
                    {canManage && <button
                        type="button"
                        onClick={handleConnect}
                        disabled={busy}
                        className="rounded-full bg-[#009ee3] px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#007ab8] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        Reconectar
                    </button>}
                </div>
            )}

            {canView && view === 'connected' && (
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-sm text-slate-600">
                        Tu cuenta está conectada{status?.mp_user_id ? ` (ID de cuenta ${status.mp_user_id})` : ''}.
                    </p>
                    {canManage && <button
                        type="button"
                        onClick={handleDisconnect}
                        disabled={busy}
                        className="rounded-full border border-red-200 px-4 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        Desconectar
                    </button>}
                </div>
            )}

            {error && <p role="alert" className="text-sm text-rose-600">{error}</p>}
            {notice && <p role="status" className="text-sm text-slate-500">{notice}</p>}
        </section>
    );
}
