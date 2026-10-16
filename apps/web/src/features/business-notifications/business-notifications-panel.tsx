'use client';

import type { Route } from 'next';
import Link from 'next/link';

import { safeInternalHref } from './api';
import { useMarkBusinessNotificationRead, useUnreadBusinessNotifications } from './hooks';
import type { BusinessNotification } from './types';

/** Texto del enlace según a dónde lleva cada tipo. */
const LINK_LABEL: Record<BusinessNotification['kind'], string> = {
    appointment_confirmed: 'Ver turno',
    appointment_payment_review: 'Ver turno',
    customer_reminder_due: 'Ver cliente',
};

/**
 * Notificaciones internas sin leer del negocio (Slice 6D): reservas
 * confirmadas por pago, pagos que requieren revisión y recordatorios de
 * clientes vencidos (CUSTOMER 07C). No conoce roles: muestra lo que devuelve
 * la API, que ya filtra por kind (manager → solo recordatorios, CUSTOMER
 * 07C.1). Si el rol no recibe ninguno (403) o no hay pendientes, no renderiza
 * nada. Se refresca cada 60 s (hooks).
 */
export function BusinessNotificationsPanel() {
    const query = useUnreadBusinessNotifications();
    const markRead = useMarkBusinessNotificationRead();
    const items = query.data?.results ?? [];

    if (!items.length) return null;

    const unread = query.data?.unread_count ?? items.length;

    return (
        <section aria-label="Notificaciones" className="space-y-2">
            <p className="text-sm font-semibold text-slate-700">
                Notificaciones {unread > items.length ? `(${items.length} de ${unread})` : `(${unread})`}
            </p>
            <ul className="space-y-2">
                {items.map((item) => (
                    <NotificationItem
                        key={item.id}
                        item={item}
                        busy={markRead.isPending && markRead.variables === item.id}
                        onRead={() => markRead.mutate(item.id)}
                    />
                ))}
            </ul>
        </section>
    );
}

function NotificationItem({
    item,
    busy,
    onRead,
}: {
    item: BusinessNotification;
    busy: boolean;
    onRead: () => void;
}) {
    const critical = item.severity === 'critical';
    const href = safeInternalHref(item.action_url);
    return (
        <li
            data-severity={item.severity}
            className={
                critical
                    ? 'rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm'
                    : 'rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm'
            }
        >
            <p className={critical ? 'font-semibold text-amber-800' : 'font-semibold text-slate-800'}>{item.title}</p>
            <p className="whitespace-pre-line text-slate-600">{item.message}</p>
            <div className="mt-2 flex flex-wrap gap-3 text-xs font-semibold">
                {href && (
                    <Link href={href as Route} onClick={onRead} className="text-slate-900 underline">
                        {LINK_LABEL[item.kind] ?? 'Ver'}
                    </Link>
                )}
                <button type="button" onClick={onRead} disabled={busy} className="text-slate-500 hover:text-slate-900">
                    Marcar como leída
                </button>
            </div>
        </li>
    );
}
