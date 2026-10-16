import { apiGet, apiPatch, apiPost, apiDelete } from '@/lib/api/client';

import type {
    Appointment,
    AppointmentCategory,
    AppointmentCategoryPayload,
    AppointmentException,
    AppointmentExceptionPayload,
    AppointmentListParams,
    AppointmentPayload,
    AppointmentProfessional,
    AppointmentProfessionalPayload,
    AppointmentSchedule,
    AppointmentSchedulePayload,
    AppointmentService,
    AppointmentServicePayload,
    AppointmentUpdatePayload,
    AvailabilityResult,
    CommunicationAutomationSettings,
    CustomerCommunicationSettings,
    ReminderAutomationSettings,
} from './types';

function buildQuery(params: Record<string, string | undefined>) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== '') {
            searchParams.append(key, value);
        }
    });
    const serialized = searchParams.toString();
    return serialized ? `?${serialized}` : '';
}

// Categories

export function fetchAppointmentCategories(params: { search?: string; includeInactive?: boolean } = {}) {
    const query = buildQuery({
        search: params.search,
        include_inactive: params.includeInactive ? 'true' : undefined,
    });
    return apiGet<AppointmentCategory[]>(`/api/v1/appointments/categories/${query}`);
}

export function createAppointmentCategory(payload: AppointmentCategoryPayload) {
    return apiPost<AppointmentCategory>('/api/v1/appointments/categories/', payload);
}

export function updateAppointmentCategory(categoryId: string, payload: Partial<AppointmentCategoryPayload>) {
    return apiPatch<AppointmentCategory>(`/api/v1/appointments/categories/${categoryId}/`, payload);
}

export function deleteAppointmentCategory(categoryId: string) {
    return apiDelete(`/api/v1/appointments/categories/${categoryId}/`);
}

// Services

export function fetchAppointmentServices(params: { search?: string; includeInactive?: boolean; category?: string | null } = {}) {
    const query = buildQuery({
        search: params.search,
        include_inactive: params.includeInactive ? 'true' : undefined,
        category: params.category === null ? 'null' : params.category,
    });
    return apiGet<AppointmentService[]>(`/api/v1/appointments/services/${query}`);
}

export function createAppointmentService(payload: AppointmentServicePayload) {
    return apiPost<AppointmentService>('/api/v1/appointments/services/', payload);
}

export function updateAppointmentService(serviceId: string, payload: Partial<AppointmentServicePayload>) {
    return apiPatch<AppointmentService>(`/api/v1/appointments/services/${serviceId}/`, payload);
}

export function deleteAppointmentService(serviceId: string) {
    return apiDelete(`/api/v1/appointments/services/${serviceId}/`);
}

// Professionals

export function fetchAppointmentProfessionals(params: { search?: string; includeInactive?: boolean } = {}) {
    const query = buildQuery({
        search: params.search,
        include_inactive: params.includeInactive ? 'true' : undefined,
    });
    return apiGet<AppointmentProfessional[]>(`/api/v1/appointments/professionals/${query}`);
}

export function createAppointmentProfessional(payload: AppointmentProfessionalPayload) {
    return apiPost<AppointmentProfessional>('/api/v1/appointments/professionals/', payload);
}

export function updateAppointmentProfessional(professionalId: string, payload: Partial<AppointmentProfessionalPayload>) {
    return apiPatch<AppointmentProfessional>(`/api/v1/appointments/professionals/${professionalId}/`, payload);
}

export function deleteAppointmentProfessional(professionalId: string) {
    return apiDelete(`/api/v1/appointments/professionals/${professionalId}/`);
}

// Schedules

export function fetchAppointmentSchedules(params: { professional?: string | null } = {}) {
    const query = buildQuery({
        professional: params.professional === null ? 'null' : params.professional,
    });
    return apiGet<AppointmentSchedule[]>(`/api/v1/appointments/schedules/${query}`);
}

export function createAppointmentSchedule(payload: AppointmentSchedulePayload) {
    return apiPost<AppointmentSchedule>('/api/v1/appointments/schedules/', payload);
}

export function updateAppointmentSchedule(scheduleId: string, payload: Partial<AppointmentSchedulePayload>) {
    return apiPatch<AppointmentSchedule>(`/api/v1/appointments/schedules/${scheduleId}/`, payload);
}

export function deleteAppointmentSchedule(scheduleId: string) {
    return apiDelete(`/api/v1/appointments/schedules/${scheduleId}/`);
}

// Exceptions

export function fetchAppointmentExceptions(params: { professional?: string | null } = {}) {
    const query = buildQuery({
        professional: params.professional === null ? 'null' : params.professional,
    });
    return apiGet<AppointmentException[]>(`/api/v1/appointments/exceptions/${query}`);
}

export function createAppointmentException(payload: AppointmentExceptionPayload) {
    return apiPost<AppointmentException>('/api/v1/appointments/exceptions/', payload);
}

export function updateAppointmentException(exceptionId: string, payload: Partial<AppointmentExceptionPayload>) {
    return apiPatch<AppointmentException>(`/api/v1/appointments/exceptions/${exceptionId}/`, payload);
}

export function deleteAppointmentException(exceptionId: string) {
    return apiDelete(`/api/v1/appointments/exceptions/${exceptionId}/`);
}

// Availability

export function fetchAppointmentAvailability(params: {
    service: string;
    date: string;
    professional?: string | null;
    excludeAppointmentId?: string | null;
}) {
    const query = buildQuery({
        service: params.service,
        date: params.date,
        professional: params.professional ?? undefined,
        exclude_appointment_id: params.excludeAppointmentId ?? undefined,
    });
    return apiGet<AvailabilityResult>(`/api/v1/appointments/availability/${query}`);
}

// Appointments (turnos)

export function fetchAppointments(params: AppointmentListParams = {}) {
    const query = buildQuery({
        date: params.date,
        date_from: params.date_from,
        date_to: params.date_to,
        professional: params.professional === null ? 'null' : params.professional,
        status: params.status,
    });
    return apiGet<Appointment[]>(`/api/v1/appointments/appointments/${query}`);
}

export function createAppointment(payload: AppointmentPayload) {
    return apiPost<Appointment>('/api/v1/appointments/appointments/', payload);
}

export function updateAppointment(appointmentId: string, payload: AppointmentUpdatePayload) {
    return apiPatch<Appointment>(`/api/v1/appointments/appointments/${appointmentId}/`, payload);
}

export function cancelAppointment(appointmentId: string) {
    return apiDelete(`/api/v1/appointments/appointments/${appointmentId}/`);
}

// ── Recordatorios automáticos (CUSTOMER 07B) ──────────────────────────────────

export function fetchReminderAutomationSettings() {
    return apiGet<ReminderAutomationSettings>('/api/v1/appointments/reminder-automation/');
}

export function updateReminderAutomationSettings(payload: Partial<ReminderAutomationSettings>) {
    return apiPatch<ReminderAutomationSettings>('/api/v1/appointments/reminder-automation/', payload);
}

// ── Email para respuestas (CUSTOMER 07D.3A.1) ─────────────────────────────────

export function fetchCustomerCommunicationSettings() {
    return apiGet<CustomerCommunicationSettings>('/api/v1/appointments/communication-settings/');
}

export function updateCustomerCommunicationSettings(payload: Partial<CustomerCommunicationSettings>) {
    return apiPatch<CustomerCommunicationSettings>('/api/v1/appointments/communication-settings/', payload);
}

// ── Comunicaciones automáticas (CUSTOMER 07D.4A) ──────────────────────────────

export type CommunicationAutomationSettingsPayload = Partial<
    Pick<CommunicationAutomationSettings, 'appointment_email_enabled' | 'no_show_email_enabled'>
>;

export function fetchCommunicationAutomationSettings() {
    return apiGet<CommunicationAutomationSettings>('/api/v1/appointments/communication-automation-settings/');
}

export function updateCommunicationAutomationSettings(payload: CommunicationAutomationSettingsPayload) {
    return apiPatch<CommunicationAutomationSettings>('/api/v1/appointments/communication-automation-settings/', payload);
}
