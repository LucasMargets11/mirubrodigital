/*
 * Notificaciones internas del negocio (Slice 6D). Owner/admin ven todos los
 * kinds; manager solo `customer_reminder_due` (CUSTOMER 07C.1). El filtro es
 * del backend: la lista y `unread_count` ya vienen recortados por rol.
 */

export type BusinessNotificationKind =
    | 'appointment_confirmed'
    | 'appointment_payment_review'
    /** CUSTOMER 07C: un recordatorio de cliente llegó a su hora; enlaza a la ficha. */
    | 'customer_reminder_due';
export type BusinessNotificationSeverity = 'info' | 'critical';

export type BusinessNotification = {
    id: string;
    kind: BusinessNotificationKind;
    severity: BusinessNotificationSeverity;
    title: string;
    message: string;
    /** Ruta interna del panel (`/app/...`) o vacío. */
    action_url: string;
    read_at: string | null;
    created_at: string;
};

export type BusinessNotificationList = {
    results: BusinessNotification[];
    unread_count: number;
};
