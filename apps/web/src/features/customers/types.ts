import type { AppointmentPaymentSummary, AppointmentStatus } from '@/features/appointments/types';
import type { OrderPaymentStatus, OrderStatus, QuoteStatus, SaleStatus } from '@/features/gestion/types';
import type { PaginatedResponse } from '@/types/api';

export type CustomerSummary = {
    id: string;
    name: string;
    doc_type: string | null;
    doc_number: string | null;
    email: string | null;
    phone: string | null;
};

export type Customer = CustomerSummary & {
    type: 'individual' | 'company';
    tax_condition: string | null;
    address_line: string | null;
    city: string | null;
    province: string | null;
    postal_code: string | null;
    country: string | null;
    note: string | null;
    tags: string[];
    is_active: boolean;
    created_at: string;
    updated_at: string;
};

/** Turno resumido dentro de `appointments_summary` (Turnos CUSTOMER 02). */
export type CustomerAppointmentRef = {
    id: string;
    start_at: string;
    end_at: string;
    /** Estado efectivo (un hold vencido llega como `expired`). */
    status: AppointmentStatus;
    service_name: string;
    professional_name: string | null;
};

/**
 * Resumen de Turnos del cliente, calculado en backend
 * (`appointments/services/customer_summary.py`). Solo viene en el detail y
 * solo si el Business tiene Turnos y el rol ve turnos; el frontend no
 * recalcula próximo/último turno.
 */
export type CustomerAppointmentsSummary = {
    total: number;
    completed: number;
    cancelled: number;
    no_show: number;
    upcoming: number;
    next_appointment: CustomerAppointmentRef | null;
    last_appointment: CustomerAppointmentRef | null;
};

/** Partición del historial de Turnos (backend `customer_history.py`). */
export type CustomerAppointmentsScope = 'upcoming' | 'history' | 'all';

/**
 * Item del historial de Turnos del cliente (Turnos CUSTOMER 03): derivado de
 * `Appointment.customer`, solo snapshots del turno. `type`/`occurred_at`
 * dejan el formato listo para una futura timeline unificada.
 */
export type CustomerAppointmentHistoryItem = {
    type: 'appointment';
    id: string;
    occurred_at: string;
    start_at: string;
    end_at: string;
    /** Estado efectivo (un hold vencido llega como `expired`). */
    status: AppointmentStatus;
    status_display: string;
    source: 'manual' | 'public';
    service_name: string;
    service_price: string;
    professional_id: string | null;
    professional_name: string | null;
    customer_name: string;
    payment_summary: AppointmentPaymentSummary | null;
    created_at: string;
};

// ── Timeline unificada (CUSTOMER 04A) ─────────────────────────────────────────

/** Fuentes de la timeline (backend `customers/timeline.py`). */
export type CustomerTimelineType = 'appointment' | 'sale' | 'quote' | 'order';

/**
 * Campos comunes de un evento: se construye al consultar desde la entidad
 * fuente (no hay tabla de eventos). `id` = `<type>:<source_id>` (único en la
 * timeline); `amount` es decimal en string o `null` si no corresponde; `href`
 * solo viene cuando existe una pantalla real.
 */
type CustomerTimelineEventBase<T extends CustomerTimelineType, S extends string, M> = {
    type: T;
    id: string;
    source_id: string;
    occurred_at: string;
    title: string;
    subtitle: string | null;
    status: S;
    status_display: string;
    amount: string | null;
    currency: string | null;
    href: string | null;
    metadata: M;
};

/** Turno (fecha canónica `start_at`); metadata = item del historial de CUSTOMER 03. */
export type AppointmentTimelineEvent = CustomerTimelineEventBase<'appointment', AppointmentStatus, CustomerAppointmentHistoryItem>;

/** Venta (fecha canónica `created_at`). */
export type SaleTimelineEvent = CustomerTimelineEventBase<
    'sale',
    SaleStatus,
    {
        number: number;
        items_count: number | null;
        payment_method: string;
        payment_method_display: string;
        cancelled_at: string | null;
        /** Factura de la venta (OneToOne), el mismo dato del detalle de venta. */
        invoice: SaleTimelineInvoice | null;
    }
>;

export type SaleTimelineInvoice = {
    id: string;
    full_number: string;
    status: 'issued' | 'voided';
    status_display: string;
};

/** Presupuesto (fecha canónica `created_at`, emisión). */
export type QuoteTimelineEvent = CustomerTimelineEventBase<
    'quote',
    QuoteStatus,
    {
        number: string;
        items_count: number | null;
        valid_until: string | null;
        sent_at: string | null;
    }
>;

/**
 * Pedido comercial (`sales.Order`, CUSTOMER 04B). Fecha canónica
 * `order_date`: el instante de alta si es ese mismo día, si no 00:00 de
 * `order_date` en la zona del Business.
 */
export type OrderTimelineEvent = CustomerTimelineEventBase<
    'order',
    OrderStatus,
    {
        number: string;
        items_count: number | null;
        order_date: string;
        estimated_delivery_date: string | null;
        payment_status: OrderPaymentStatus;
        payment_status_display: string;
        total_paid: string;
        pending_balance: string;
    }
>;

export type CustomerTimelineEvent = AppointmentTimelineEvent | SaleTimelineEvent | QuoteTimelineEvent | OrderTimelineEvent;

/** Página de la timeline; `types` = fuentes efectivamente incluidas (módulos + permisos). */
export type CustomerTimelinePage = PaginatedResponse<CustomerTimelineEvent> & {
    types: CustomerTimelineType[];
};

/**
 * Nota interna del equipo sobre el cliente (CUSTOMER 04C). Nunca visible
 * para el cliente; `author` es null si el usuario fue eliminado.
 */
export type CustomerNote = {
    id: string;
    body: string;
    author: { id: string; name: string } | null;
    created_at: string;
    updated_at: string;
};

/** Mismo límite que backend (`CustomerNote.BODY_MAX_LENGTH`). */
export const CUSTOMER_NOTE_MAX_LENGTH = 2000;

/**
 * Recordatorio interno del equipo (CUSTOMER 07A). No se envía al cliente.
 * `completed`/`cancelled` son finales. "Vencido" NO es un estado: es
 * `is_overdue` (pending con `remind_at` pasado), derivado por el backend.
 * Las fechas llegan con el offset de `Business.timezone`.
 */
export type CustomerReminderStatus = 'pending' | 'completed' | 'cancelled';

export type CustomerReminderSource = 'manual' | 'appointment_upcoming' | 'no_show_followup';

export type CustomerReminder = {
    id: string;
    title: string;
    description: string;
    remind_at: string;
    status: CustomerReminderStatus;
    status_display: string;
    is_overdue: boolean;
    /** CUSTOMER 07B: los automáticos solo se completan/cancelan (el backend rechaza editarlos). */
    source: CustomerReminderSource;
    source_display: string;
    is_automatic: boolean;
    appointment_id: string | null;
    appointment_start_at: string | null;
    created_by: { id: string; name: string } | null;
    completed_at: string | null;
    /** CUSTOMER 07C: cuándo salió el aviso interno al vencer. NO es un estado ni completa el recordatorio. */
    notified_at: string | null;
    created_at: string;
    updated_at: string;
};

/** `pending` (default, más próximo primero) | `closed` (completados + cancelados, más recientes primero) | `all`. */
export type CustomerRemindersScope = 'pending' | 'closed' | 'all';

export type CustomerRemindersPage = PaginatedResponse<CustomerReminder> & {
    counts: { pending: number; closed: number };
};

/**
 * `remind_at` sin offset ("YYYY-MM-DDTHH:mm") = hora local del Business; el
 * backend lo interpreta en `Business.timezone` (nunca la zona del navegador).
 */
export type CustomerReminderPayload = {
    title: string;
    description?: string;
    remind_at: string;
    appointment_id?: string | null;
};

/** Mismos límites que backend (`CustomerReminder.TITLE_MAX_LENGTH` / `DESCRIPTION_MAX_LENGTH`). */
export const CUSTOMER_REMINDER_TITLE_MAX_LENGTH = 200;
export const CUSTOMER_REMINDER_DESCRIPTION_MAX_LENGTH = 2000;

/**
 * Preferencias de contacto OPERATIVO del cliente (CUSTOMER 07D.1). No
 * incluye marketing. Nada se envía todavía: es la base para 07D.2.
 * WhatsApp/email arrancan apagados; encenderlos exige confirmar
 * consentimiento (`*_consent_confirmed`). Apagar conserva `*_consent_at`.
 * `do_not_contact` gana sobre todo. `channels` lo deriva el backend: un canal
 * permitido sin teléfono/email válido NO es usable.
 */
export type ContactChannel = 'whatsapp' | 'email' | 'phone';

/**
 * Primera razón por la que el canal no es usable (orden del backend).
 * CUSTOMER 07D.1.1: `consent_missing` (no hay destino autorizado registrado) y
 * `consent_destination_changed` (el teléfono/email actual no es el que se
 * autorizó) piden renovar la autorización. El frontend no recalcula la regla.
 */
export type ContactChannelReason =
    | 'do_not_contact'
    | 'disabled'
    | 'missing_phone'
    | 'invalid_phone'
    | 'missing_email'
    | 'consent_missing'
    | 'consent_destination_changed';

export type ContactConsentSource = 'manual' | 'customer_request' | 'public_booking' | 'imported';

export type CustomerContactPreferences = {
    customer_id: string;
    whatsapp_enabled: boolean;
    email_enabled: boolean;
    /** Llamadas: canal manual (nunca automático), permitido por defecto. */
    phone_enabled: boolean;
    preferred_channel: ContactChannel | null;
    do_not_contact: boolean;
    whatsapp_consent_at: string | null;
    whatsapp_consent_source: ContactConsentSource | null;
    email_consent_at: string | null;
    email_consent_source: ContactConsentSource | null;
    channels: Record<ContactChannel, { usable: boolean; reason: ContactChannelReason | null }>;
    /** `null` = todavía nadie las editó (defaults). */
    updated_at: string | null;
};

export type CustomerContactPreferencesPayload = Partial<
    Pick<CustomerContactPreferences, 'whatsapp_enabled' | 'email_enabled' | 'phone_enabled' | 'preferred_channel' | 'do_not_contact'>
> & {
    /** Al encender el canal es obligatorio; con el canal ya encendido RENUEVA la autorización contra el destino actual. */
    whatsapp_consent_confirmed?: boolean;
    email_consent_confirmed?: boolean;
    /** Desde el panel solo `manual` | `customer_request`. */
    consent_source?: 'manual' | 'customer_request';
};

export type CustomerDetail = Customer & {
    appointments_summary?: CustomerAppointmentsSummary;
};

export type CustomerPayload = {
    name: string;
    type?: Customer['type'];
    doc_type?: string;
    doc_number?: string;
    tax_condition?: string;
    email?: string;
    phone?: string;
    address_line?: string;
    city?: string;
    province?: string;
    postal_code?: string;
    country?: string;
    note?: string;
    is_active?: boolean;
};

export type CustomerFilters = {
    search?: string;
    includeInactive?: boolean;
    limit?: number;
    offset?: number;
};

/**
 * Comunicación externa al cliente (CUSTOMER 07D.2). Solo historial/auditoría:
 * se crean y ejecutan en el backend (hoy con proveedores fake, sin envío real).
 * El destino llega enmascarado desde el backend; nunca el completo.
 */
export type CustomerDeliveryChannel = 'whatsapp' | 'email';
export type CustomerDeliveryPurpose = 'appointment_reminder' | 'no_show_followup';
export type CustomerDeliveryStatus = 'pending' | 'processing' | 'sent' | 'delivered' | 'failed' | 'skipped' | 'cancelled';

export type CustomerDelivery = {
    id: string;
    channel: CustomerDeliveryChannel;
    channel_display: string;
    purpose: CustomerDeliveryPurpose;
    purpose_display: string;
    status: CustomerDeliveryStatus;
    status_display: string;
    destination_masked: string | null;
    attempt_count: number;
    max_attempts: number;
    /** Lo procesó un proveedor fake (sin envío real). */
    is_simulated: boolean;
    /** Proveedor real que lo envió (p. ej. "Amazon SES"); null si fake o sin intento. */
    provider_display?: string | null;
    /** Motivo de negocio de un `skipped` (opt-out, canal apagado, consentimiento, destino). */
    skip_reason: string | null;
    /** Código técnico del último fallo del proveedor. */
    failure_code: string | null;
    appointment_id: string | null;
    reminder_id: string | null;
    created_at: string;
    last_attempt_at: string | null;
    next_retry_at: string | null;
    sent_at: string | null;
    delivered_at: string | null;
    failed_at: string | null;
    skipped_at: string | null;
    cancelled_at: string | null;
};
