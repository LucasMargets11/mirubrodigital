/* ── Turnos domain types (categorías + servicios) ─────────────────────── */

export type AppointmentCategory = {
    id: string;
    name: string;
    description: string;
    is_active: boolean;
    sort_order: number;
    services_count: number;
    created_at: string;
    updated_at: string;
};

export type AppointmentCategorySummary = {
    id: string;
    name: string;
};

export type AppointmentCategoryPayload = {
    name: string;
    description?: string;
    is_active?: boolean;
    sort_order?: number;
};

export type DepositType = 'none' | 'fixed' | 'percentage';

export type AppointmentService = {
    id: string;
    category: AppointmentCategorySummary | null;
    name: string;
    description: string;
    duration_minutes: number;
    price: string;
    deposit_type: DepositType;
    deposit_value: string;
    is_active: boolean;
    sort_order: number;
    created_at: string;
    updated_at: string;
};

export type AppointmentServicePayload = {
    category_id?: string | null;
    name: string;
    description?: string;
    duration_minutes: number;
    price: number;
    deposit_type: DepositType;
    deposit_value: number;
    is_active?: boolean;
    sort_order?: number;
};

export type AppointmentServiceSummary = {
    id: string;
    name: string;
    duration_minutes: number;
    price: string;
    is_active: boolean;
    category: AppointmentCategorySummary | null;
};

export type AppointmentProfessionalSummary = {
    id: string;
    name: string;
};

export type AppointmentProfessional = {
    id: string;
    name: string;
    description: string;
    phone: string;
    email: string;
    services: AppointmentServiceSummary[];
    is_active: boolean;
    sort_order: number;
    created_at: string;
    updated_at: string;
};

export type AppointmentProfessionalPayload = {
    name: string;
    description?: string;
    phone?: string;
    email?: string;
    service_ids?: string[];
    is_active?: boolean;
    sort_order?: number;
};

/* ── Horarios (semanal + excepciones) ─────────────────────────────────── */

export type Weekday = 0 | 1 | 2 | 3 | 4 | 5 | 6;

export const WEEKDAYS: { value: Weekday; label: string }[] = [
    { value: 0, label: 'Lunes' },
    { value: 1, label: 'Martes' },
    { value: 2, label: 'Miércoles' },
    { value: 3, label: 'Jueves' },
    { value: 4, label: 'Viernes' },
    { value: 5, label: 'Sábado' },
    { value: 6, label: 'Domingo' },
];

export type AppointmentSchedule = {
    id: string;
    professional: AppointmentProfessionalSummary | null;
    weekday: Weekday;
    weekday_display: string;
    start_time: string;
    end_time: string;
    created_at: string;
    updated_at: string;
};

export type AppointmentSchedulePayload = {
    professional_id?: string | null;
    weekday: Weekday;
    start_time: string;
    end_time: string;
};

export type AppointmentException = {
    id: string;
    professional: AppointmentProfessionalSummary | null;
    date: string;
    is_closed: boolean;
    start_time: string | null;
    end_time: string | null;
    note: string;
    created_at: string;
    updated_at: string;
};

export type AppointmentExceptionPayload = {
    professional_id?: string | null;
    date: string;
    is_closed: boolean;
    start_time?: string | null;
    end_time?: string | null;
    note?: string;
};

/* ── Disponibilidad ────────────────────────────────────────────────────── */

export type AvailabilitySlot = {
    start: string;
    end: string;
};

export type AvailabilityResult = {
    date: string;
    service: string;
    professional: string | null;
    slots: AvailabilitySlot[];
};

/* ── Turnos (Appointment) ─────────────────────────────────────────────── */

export type AppointmentStatus =
    | 'pending_payment'
    | 'confirmed'
    | 'completed'
    | 'cancelled'
    | 'no_show'
    | 'expired';

export const APPOINTMENT_STATUS_LABELS: Record<AppointmentStatus, string> = {
    pending_payment: 'Pendiente de pago',
    confirmed: 'Confirmado',
    completed: 'Completado',
    cancelled: 'Cancelado',
    no_show: 'No asistió',
    expired: 'Vencido',
};

/** Estados de `AppointmentPayment` (Slice 6A/6B). */
export type AppointmentPaymentStatus =
    | 'creating'
    | 'pending'
    | 'approved'
    | 'rejected'
    | 'cancelled'
    | 'error'
    | 'uncertain'
    | 'requires_review';

/** Motivos de `requires_review` (códigos estables del backend, Slice 6B). */
export type AppointmentPaymentReviewReason =
    | 'approved_after_expiry'
    | 'approval_time_unknown'
    | 'slot_conflict'
    | 'appointment_already_confirmed'
    | 'appointment_not_payable';

/**
 * Resumen financiero del intento de pago representativo del turno (Slice 7B.3).
 * Elegido server-side (`services.payment_summary`); el frontend solo lo
 * representa. Nunca incluye ids de Mercado Pago ni referencias.
 */
export type AppointmentPaymentSummary = {
    status: AppointmentPaymentStatus;
    amount: string;
    currency: string;
    paid_at: string | null;
    requires_review: boolean;
    review_reason: AppointmentPaymentReviewReason | null;
};

export type Appointment = {
    id: string;
    service: AppointmentServiceSummary;
    professional: AppointmentProfessionalSummary | null;
    /** `Customer` canónico vinculado (null en turnos legacy). La UI muestra los snapshots `customer_*`. */
    customer_id: string | null;
    customer_name: string;
    customer_phone: string;
    customer_email: string;
    start_at: string;
    end_at: string;
    /** Estado almacenado. Para mostrar, usar siempre `effective_status`. */
    status: AppointmentStatus;
    status_display: string;
    /** Estado real calculado por el backend (hold vencido → `expired`). */
    effective_status: AppointmentStatus;
    effective_status_display: string;
    /** Vencimiento del hold de `pending_payment`; null en otros estados. */
    expires_at: string | null;
    payment_summary: AppointmentPaymentSummary | null;
    notes: string;
    source: 'manual' | 'public';
    service_name: string;
    service_duration_minutes: number;
    service_price: string;
    deposit_type: DepositType;
    deposit_value: string;
    created_at: string;
    updated_at: string;
};

export type AppointmentPayload = {
    service_id: string;
    professional_id?: string | null;
    start_at: string;
    /**
     * Customer elegido en el CustomerPicker (CUSTOMER 05): mismo Business y
     * activo. Si viene, es el vínculo y el backend NO resuelve por teléfono;
     * omitido → resolver por teléfono de CUSTOMER 01. Los `customer_*` siguen
     * siendo snapshots del turno (nunca modifican el Customer).
     */
    customer_id?: string;
    customer_name: string;
    customer_phone: string;
    customer_email?: string;
    notes?: string;
};

export type AppointmentUpdatePayload = Partial<AppointmentPayload> & {
    status?: AppointmentStatus;
};

/** Filtros del listado interno: un día (`date`) o un rango inclusive (`date_from`/`date_to`, Slice 7D). */
export type AppointmentListParams = {
    date?: string;
    date_from?: string;
    date_to?: string;
    professional?: string | null;
    status?: AppointmentStatus;
};

/* ── Landing pública `/t/[slug]` (Slice 4A) ───────────────────────────── */

export type PublicAppointmentCategory = {
    id: string;
    name: string;
    description: string;
};

export type PublicAppointmentCategorySummary = {
    id: string;
    name: string;
};

export type PublicAppointmentService = {
    id: string;
    name: string;
    description: string;
    duration_minutes: number;
    price: string;
    deposit_type: DepositType;
    deposit_value: string;
    category: PublicAppointmentCategorySummary | null;
};

export type PublicAppointmentProfessional = {
    id: string;
    name: string;
    description: string;
};

export type PublicAppointmentBusiness = {
    business: {
        name: string;
        slug: string;
        timezone: string;
    };
    categories: PublicAppointmentCategory[];
    services: PublicAppointmentService[];
};

/* ── Reserva pública `/t/[slug]` (Slice 4B) ───────────────────────────── */

export type PublicBookingStatus =
    | 'pending_payment'
    | 'confirmed'
    | 'expired'
    | 'cancelled'
    | 'completed'
    | 'no_show';

/**
 * Estado público normalizado del intento de pago relevante (Slice 6C).
 * `null` = todavía no se inició ningún pago. Nunca incluye ids de Mercado
 * Pago ni motivos internos.
 */
export type PublicBookingPaymentStatus =
    | 'creating'
    | 'pending'
    | 'approved'
    | 'rejected'
    | 'cancelled'
    | 'error'
    | 'uncertain'
    | 'requires_review';

export type PublicAppointmentBookingPayload = {
    service: string;
    professional?: string | null;
    start: string;
    customer_name: string;
    customer_phone: string;
    customer_email?: string;
};

export type PublicAppointmentBooking = {
    public_token: string;
    status: PublicBookingStatus;
    expires_at: string | null;
    start_at: string;
    end_at: string;
    customer_name: string;
    service: {
        name: string;
        price: string;
        duration_minutes: number;
    };
    professional: { name: string } | null;
    deposit_amount: string;
    payment_status: PublicBookingPaymentStatus | null;
    /**
     * Slice 6D: link `https://wa.me/...` con mensaje prearmado, armado por el
     * backend solo para `confirmed` / `requires_review` y si el negocio tiene
     * WhatsApp configurado. null en cualquier otro caso.
     */
    contact_whatsapp_url?: string | null;
};

/* ── Checkout de seña (Slice 6A) ──────────────────────────────────────────
 * Respuesta de `POST /api/v1/appointments/public/<slug>/bookings/<public_token>/checkout/`
 * (body vacío: monto/moneda/referencia se derivan server-side). Usado por el
 * botón "Continuar al pago" (Slice 6C, ver `public-booking.ts`).
 */
export type PublicAppointmentCheckout = {
    payment_id: string;
    status: 'pending';
    amount: string;
    currency: string;
    checkout_url: string;
    expires_at: string;
};

export type PublicAppointmentCheckoutErrorCode =
    | 'not_payable'
    | 'expired'
    | 'payment_in_progress'
    | 'payment_unavailable'
    | 'payment_provider_error'
    | 'payment_uncertain';

/**
 * Recordatorios internos automáticos (CUSTOMER 07B). Apagados por defecto.
 * Solo crean recordatorios para el equipo: nunca se envía nada al cliente.
 */
export type ReminderAutomationSettings = {
    appointment_reminder_enabled: boolean;
    appointment_reminder_hours_before: number;
    no_show_followup_enabled: boolean;
    no_show_followup_delay_hours: number;
    updated_at?: string;
};

/** Mismos límites que el backend (`CustomerReminderAutomationSettings`). */
export const REMINDER_AUTOMATION_LIMITS = {
    appointment_reminder_hours_before: { min: 1, max: 168 },
    no_show_followup_delay_hours: { min: 1, max: 720 },
} as const;

/**
 * Comunicaciones al cliente (CUSTOMER 07D.3A.1): email operativo al que llegan
 * las respuestas (Reply-To). Vacío = los emails salen sin Reply-To.
 */
export type CustomerCommunicationSettings = {
    reply_to_email: string;
    updated_at?: string;
};

/**
 * Comunicaciones automáticas al cliente por email (CUSTOMER 07D.4A). Apagadas
 * por defecto. `email_delivery_mode` lo decide el entorno del backend:
 * `simulation` = proveedor fake (nada sale), `live` = proveedor real activo.
 */
export type CommunicationAutomationSettings = {
    appointment_email_enabled: boolean;
    no_show_email_enabled: boolean;
    email_delivery_mode: 'simulation' | 'live';
    updated_at?: string;
};
