import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
    cancelAppointment,
    createAppointment,
    createAppointmentCategory,
    createAppointmentException,
    createAppointmentProfessional,
    createAppointmentSchedule,
    createAppointmentService,
    deleteAppointmentCategory,
    deleteAppointmentException,
    deleteAppointmentProfessional,
    deleteAppointmentSchedule,
    deleteAppointmentService,
    fetchAppointmentAvailability,
    fetchAppointmentCategories,
    fetchAppointmentExceptions,
    fetchAppointmentProfessionals,
    fetchAppointmentSchedules,
    fetchAppointmentServices,
    fetchAppointments,
    updateAppointment,
    updateAppointmentCategory,
    updateAppointmentException,
    updateAppointmentProfessional,
    updateAppointmentSchedule,
    updateAppointmentService,
    fetchCommunicationAutomationSettings,
    fetchCustomerCommunicationSettings,
    fetchReminderAutomationSettings,
    updateCommunicationAutomationSettings,
    updateCustomerCommunicationSettings,
    updateReminderAutomationSettings,
} from './api';
import type { CommunicationAutomationSettingsPayload } from './api';
import type {
    AppointmentCategoryPayload,
    AppointmentExceptionPayload,
    AppointmentListParams,
    AppointmentPayload,
    AppointmentProfessionalPayload,
    AppointmentSchedulePayload,
    AppointmentServicePayload,
    AppointmentUpdatePayload,
    CustomerCommunicationSettings,
    ReminderAutomationSettings,
} from './types';

const categoriesBaseKey = ['appointments', 'categories'];
const servicesBaseKey = ['appointments', 'services'];
const professionalsBaseKey = ['appointments', 'professionals'];
const schedulesBaseKey = ['appointments', 'schedules'];
const exceptionsBaseKey = ['appointments', 'exceptions'];
const appointmentsBaseKey = ['appointments', 'appointments'];
const availabilityBaseKey = ['appointments', 'availability'];

// Categories

export function useAppointmentCategories(search: string = '', includeInactive: boolean = false, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: [...categoriesBaseKey, { search, includeInactive }],
        queryFn: () => fetchAppointmentCategories({ search, includeInactive }),
        enabled: options?.enabled ?? true,
    });
}

export function useCreateAppointmentCategory() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: AppointmentCategoryPayload) => createAppointmentCategory(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: categoriesBaseKey });
        },
    });
}

export function useUpdateAppointmentCategory() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: Partial<AppointmentCategoryPayload> }) =>
            updateAppointmentCategory(id, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: categoriesBaseKey });
            queryClient.invalidateQueries({ queryKey: servicesBaseKey });
        },
    });
}

export function useDeleteAppointmentCategory() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (id: string) => deleteAppointmentCategory(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: categoriesBaseKey });
        },
    });
}

// Services

export function useAppointmentServices(search: string, includeInactive: boolean, category?: string | null, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: [...servicesBaseKey, { search, includeInactive, category }],
        queryFn: () => fetchAppointmentServices({ search, includeInactive, category }),
        enabled: options?.enabled ?? true,
    });
}

export function useCreateAppointmentService() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: AppointmentServicePayload) => createAppointmentService(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: servicesBaseKey });
            queryClient.invalidateQueries({ queryKey: categoriesBaseKey });
        },
    });
}

export function useUpdateAppointmentService() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: Partial<AppointmentServicePayload> }) =>
            updateAppointmentService(id, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: servicesBaseKey });
            queryClient.invalidateQueries({ queryKey: categoriesBaseKey });
        },
    });
}

export function useDeleteAppointmentService() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (id: string) => deleteAppointmentService(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: servicesBaseKey });
            queryClient.invalidateQueries({ queryKey: categoriesBaseKey });
        },
    });
}

// Professionals

export function useAppointmentProfessionals(search: string = '', includeInactive: boolean = false, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: [...professionalsBaseKey, { search, includeInactive }],
        queryFn: () => fetchAppointmentProfessionals({ search, includeInactive }),
        enabled: options?.enabled ?? true,
    });
}

export function useCreateAppointmentProfessional() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: AppointmentProfessionalPayload) => createAppointmentProfessional(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: professionalsBaseKey });
        },
    });
}

export function useUpdateAppointmentProfessional() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: Partial<AppointmentProfessionalPayload> }) =>
            updateAppointmentProfessional(id, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: professionalsBaseKey });
        },
    });
}

export function useDeleteAppointmentProfessional() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (id: string) => deleteAppointmentProfessional(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: professionalsBaseKey });
        },
    });
}

// Schedules

export function useAppointmentSchedules(professional?: string | null, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: [...schedulesBaseKey, { professional }],
        queryFn: () => fetchAppointmentSchedules({ professional }),
        enabled: options?.enabled ?? true,
    });
}

export function useCreateAppointmentSchedule() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: AppointmentSchedulePayload) => createAppointmentSchedule(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: schedulesBaseKey });
        },
    });
}

export function useUpdateAppointmentSchedule() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: Partial<AppointmentSchedulePayload> }) =>
            updateAppointmentSchedule(id, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: schedulesBaseKey });
        },
    });
}

export function useDeleteAppointmentSchedule() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (id: string) => deleteAppointmentSchedule(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: schedulesBaseKey });
        },
    });
}

// Exceptions

export function useAppointmentExceptions(professional?: string | null, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: [...exceptionsBaseKey, { professional }],
        queryFn: () => fetchAppointmentExceptions({ professional }),
        enabled: options?.enabled ?? true,
    });
}

export function useCreateAppointmentException() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: AppointmentExceptionPayload) => createAppointmentException(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: exceptionsBaseKey });
        },
    });
}

export function useUpdateAppointmentException() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: Partial<AppointmentExceptionPayload> }) =>
            updateAppointmentException(id, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: exceptionsBaseKey });
        },
    });
}

export function useDeleteAppointmentException() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (id: string) => deleteAppointmentException(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: exceptionsBaseKey });
        },
    });
}

// Availability

export function useAppointmentAvailability(
    params: { service: string; date: string; professional?: string | null; excludeAppointmentId?: string | null },
    options?: { enabled?: boolean },
) {
    return useQuery({
        queryKey: [...availabilityBaseKey, params],
        queryFn: () => fetchAppointmentAvailability(params),
        enabled: options?.enabled ?? Boolean(params.service && params.date),
    });
}

// Appointments (turnos)

export function useAppointments(
    params: AppointmentListParams = {},
    options?: { enabled?: boolean },
) {
    return useQuery({
        queryKey: [...appointmentsBaseKey, params],
        queryFn: () => fetchAppointments(params),
        enabled: options?.enabled ?? true,
    });
}

export function useCreateAppointment() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: AppointmentPayload) => createAppointment(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: appointmentsBaseKey });
        },
    });
}

export function useUpdateAppointment() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: AppointmentUpdatePayload }) =>
            updateAppointment(id, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: appointmentsBaseKey });
        },
    });
}

export function useCancelAppointment() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (id: string) => cancelAppointment(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: appointmentsBaseKey });
        },
    });
}

// ── Recordatorios automáticos (CUSTOMER 07B) ──────────────────────────────────

const reminderAutomationKey = ['appointments', 'reminder-automation'];

export function useReminderAutomationSettings(options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: reminderAutomationKey,
        queryFn: fetchReminderAutomationSettings,
        enabled: options?.enabled ?? true,
    });
}

export function useUpdateReminderAutomationSettings() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: Partial<ReminderAutomationSettings>) => updateReminderAutomationSettings(payload),
        onSuccess: (data) => queryClient.setQueryData(reminderAutomationKey, data),
    });
}

// ── Email para respuestas (CUSTOMER 07D.3A.1) ─────────────────────────────────

const communicationSettingsKey = ['appointments', 'communication-settings'];

export function useCustomerCommunicationSettings(options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: communicationSettingsKey,
        queryFn: fetchCustomerCommunicationSettings,
        enabled: options?.enabled ?? true,
    });
}

export function useUpdateCustomerCommunicationSettings() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: Partial<CustomerCommunicationSettings>) => updateCustomerCommunicationSettings(payload),
        onSuccess: (data) => queryClient.setQueryData(communicationSettingsKey, data),
    });
}

// ── Comunicaciones automáticas (CUSTOMER 07D.4A) ──────────────────────────────

const communicationAutomationKey = ['appointments', 'communication-automation-settings'];

export function useCommunicationAutomationSettings(options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: communicationAutomationKey,
        queryFn: fetchCommunicationAutomationSettings,
        enabled: options?.enabled ?? true,
    });
}

export function useUpdateCommunicationAutomationSettings() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: CommunicationAutomationSettingsPayload) => updateCommunicationAutomationSettings(payload),
        onSuccess: (data) => queryClient.setQueryData(communicationAutomationKey, data),
    });
}
