import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';

import {
    createCustomer,
    createCustomerNote,
    createCustomerReminder,
    deleteCustomerNote,
    getCustomer,
    getCustomerAppointments,
    getCustomerContactPreferences,
    getCustomerTimeline,
    listCustomerDeliveries,
    listCustomerNotes,
    listCustomerReminders,
    listCustomers,
    updateCustomer,
    updateCustomerContactPreferences,
    updateCustomerNote,
    updateCustomerReminder,
} from './api';
import type {
    CustomerAppointmentsScope,
    CustomerContactPreferencesPayload,
    CustomerFilters,
    CustomerPayload,
    CustomerReminderPayload,
    CustomerRemindersScope,
    CustomerTimelineType,
} from './types';

const customersBaseKey = ['gestion', 'customers'];

export function useCustomers(filters: CustomerFilters, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: [...customersBaseKey, filters],
        queryFn: () => listCustomers(filters),
        enabled: options?.enabled ?? true,
    });
}

export function useCustomer(id: string) {
    return useQuery({
        queryKey: [...customersBaseKey, id],
        queryFn: () => getCustomer(id),
        enabled: !!id,
    });
}

export function useCustomerAppointments(
    customerId: string,
    params: { scope: CustomerAppointmentsScope; limit?: number; offset?: number },
    options?: { enabled?: boolean },
) {
    return useQuery({
        queryKey: [...customersBaseKey, customerId, 'appointments', params],
        queryFn: () => getCustomerAppointments(customerId, params),
        enabled: (options?.enabled ?? true) && !!customerId,
    });
}

export function useCustomerTimeline(
    customerId: string,
    params: { types?: CustomerTimelineType[]; limit?: number; offset?: number },
    options?: { enabled?: boolean },
) {
    return useQuery({
        queryKey: [...customersBaseKey, customerId, 'timeline', params],
        queryFn: () => getCustomerTimeline(customerId, params),
        enabled: (options?.enabled ?? true) && !!customerId,
        // 403 = ninguna fuente visible para este rol/plan: no reintentar.
        retry: false,
    });
}

/**
 * CUSTOMER 06: tras crear un turno desde la ficha, refresca solo lo que lo
 * muestra (ficha con `appointments_summary`, próximos turnos y timeline).
 * CUSTOMER 07B: también los recordatorios (el turno puede generar uno
 * automático). Notas y listado de Clientes quedan intactos.
 */
export function useRefreshCustomerAppointmentViews(customerId: string) {
    const queryClient = useQueryClient();
    return useCallback(
        () =>
            Promise.all([
                queryClient.invalidateQueries({ queryKey: [...customersBaseKey, customerId], exact: true }),
                queryClient.invalidateQueries({ queryKey: [...customersBaseKey, customerId, 'appointments'] }),
                queryClient.invalidateQueries({ queryKey: [...customersBaseKey, customerId, 'timeline'] }),
                queryClient.invalidateQueries({ queryKey: [...customersBaseKey, customerId, 'reminders'] }),
            ]),
        [queryClient, customerId],
    );
}

export function useCreateCustomer() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: CustomerPayload) => createCustomer(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: customersBaseKey });
        },
    });
}

export function useUpdateCustomer() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: Partial<CustomerPayload> }) => updateCustomer(id, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: customersBaseKey });
        },
    });
}

// ── Notas internas (CUSTOMER 04C) ────────────────────────────────────────────
// Las mutaciones invalidan SOLO la lista de notas: la ficha y la timeline no se re-fetchean.

function customerNotesKey(customerId: string) {
    return [...customersBaseKey, customerId, 'notes'];
}

export function useCustomerNotes(customerId: string, params: { limit?: number } = {}) {
    return useQuery({
        queryKey: [...customerNotesKey(customerId), params],
        queryFn: () => listCustomerNotes(customerId, params),
        enabled: !!customerId,
    });
}

export function useCreateCustomerNote(customerId: string) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (body: string) => createCustomerNote(customerId, body),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: customerNotesKey(customerId) }),
    });
}

export function useUpdateCustomerNote(customerId: string) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ noteId, body }: { noteId: string; body: string }) => updateCustomerNote(customerId, noteId, body),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: customerNotesKey(customerId) }),
    });
}

export function useDeleteCustomerNote(customerId: string) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (noteId: string) => deleteCustomerNote(customerId, noteId),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: customerNotesKey(customerId) }),
    });
}

// ── Recordatorios internos (CUSTOMER 07A) ────────────────────────────────────
// Las mutaciones invalidan SOLO los recordatorios del cliente (pendientes y
// cerrados): ni la ficha, ni la timeline, ni las notas.

function customerRemindersKey(customerId: string) {
    return [...customersBaseKey, customerId, 'reminders'];
}

export function useCustomerReminders(
    customerId: string,
    params: { scope?: CustomerRemindersScope; limit?: number } = {},
    options?: { enabled?: boolean },
) {
    return useQuery({
        queryKey: [...customerRemindersKey(customerId), params],
        queryFn: () => listCustomerReminders(customerId, params),
        enabled: !!customerId && (options?.enabled ?? true),
    });
}

export function useCreateCustomerReminder(customerId: string) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: CustomerReminderPayload) => createCustomerReminder(customerId, payload),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: customerRemindersKey(customerId) }),
    });
}

export function useUpdateCustomerReminder(customerId: string) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({
            reminderId,
            payload,
        }: {
            reminderId: string;
            payload: Partial<CustomerReminderPayload> & { status?: 'completed' | 'cancelled' };
        }) => updateCustomerReminder(customerId, reminderId, payload),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: customerRemindersKey(customerId) }),
    });
}

// ── Preferencias de contacto (CUSTOMER 07D.1) ───────────────────────────────
// Editar la ficha (`useUpdateCustomer`) invalida todo el prefijo del cliente,
// así que `channels` se recalcula si cambia el teléfono/email.

function customerContactPreferencesKey(customerId: string) {
    return [...customersBaseKey, customerId, 'contact-preferences'];
}

export function useCustomerContactPreferences(customerId: string) {
    return useQuery({
        queryKey: customerContactPreferencesKey(customerId),
        queryFn: () => getCustomerContactPreferences(customerId),
        enabled: !!customerId,
    });
}

export function useUpdateCustomerContactPreferences(customerId: string) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: CustomerContactPreferencesPayload) => updateCustomerContactPreferences(customerId, payload),
        onSuccess: (data) => queryClient.setQueryData(customerContactPreferencesKey(customerId), data),
    });
}

// ── Comunicaciones externas (CUSTOMER 07D.2): solo lectura, sin mutaciones ──

export function useCustomerDeliveries(customerId: string, params: { limit?: number } = {}) {
    return useQuery({
        queryKey: [...customersBaseKey, customerId, 'deliveries', params],
        queryFn: () => listCustomerDeliveries(customerId, params),
        enabled: !!customerId,
    });
}
