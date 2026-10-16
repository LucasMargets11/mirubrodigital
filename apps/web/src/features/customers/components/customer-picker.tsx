"use client";

import { useEffect, useState } from 'react';

import { useCustomer, useCustomers } from '../hooks';
import type { Customer } from '../types';
import { CustomerFormModal } from './customer-form-modal';

/** Mínimo de caracteres antes de buscar y debounce del input. */
export const CUSTOMER_PICKER_MIN_CHARS = 2;
export const CUSTOMER_PICKER_DEBOUNCE_MS = 300;
const RESULTS_LIMIT = 8;

/**
 * Customer elegido. Con solo `id` (p.ej. al editar un turno ya vinculado) el
 * picker trae nombre/teléfono de la ficha; tras buscar o crear ya vienen.
 */
export type PickedCustomer = {
    id: string;
    name?: string;
    phone?: string | null;
    email?: string | null;
    is_active?: boolean;
};

type CustomerPickerProps = {
    value: PickedCustomer | null;
    /** Al elegir un resultado o crear uno nuevo (nunca al solo abrir/editar). */
    onSelect: (customer: Customer) => void;
    /** `manage_customers`/`create_sales`: muestra "+ Crear nuevo cliente". El backend valida igual. */
    canCreate: boolean;
    error?: string;
    /** Ayuda bajo el buscador vacío cuando no hay Customer elegido (default: texto del alta de turno). */
    emptyHint?: string;
};

/**
 * Buscador del Customer canónico (Turnos CUSTOMER 05). Reutiliza
 * `GET /api/v1/customers/?search=` (nombre/teléfono/email, solo activos del
 * Business) y `CustomerFormModal` para el alta inline. No carga el padrón:
 * debounce + mínimo de caracteres + `limit`; los resultados mostrados son
 * siempre los del término actual (las respuestas viejas quedan en otra key).
 */
export function CustomerPicker({ value, onSelect, canCreate, error, emptyHint }: CustomerPickerProps) {
    const [changing, setChanging] = useState(false);
    const [term, setTerm] = useState('');
    const [debouncedTerm, setDebouncedTerm] = useState('');
    const [createOpen, setCreateOpen] = useState(false);

    useEffect(() => {
        const handle = window.setTimeout(() => setDebouncedTerm(term.trim()), CUSTOMER_PICKER_DEBOUNCE_MS);
        return () => window.clearTimeout(handle);
    }, [term]);

    const searchEnabled = debouncedTerm.length >= CUSTOMER_PICKER_MIN_CHARS;
    const searchQuery = useCustomers({ search: debouncedTerm, limit: RESULTS_LIMIT }, { enabled: searchEnabled });
    const pending = term.trim() !== debouncedTerm;
    const results = searchQuery.data?.results ?? [];

    // Turno ya vinculado: la tarjeta muestra la ficha, no el snapshot.
    const needsDetail = Boolean(value && value.name === undefined);
    const detailQuery = useCustomer(needsDetail && value ? value.id : '');
    const shown = needsDetail ? detailQuery.data : value;

    function select(customer: Customer) {
        onSelect(customer);
        setChanging(false);
        setTerm('');
        setDebouncedTerm('');
    }

    const createModal = createOpen ? (
        <CustomerFormModal
            mode="create"
            canSubmit={canCreate}
            initialValues={initialValuesFromTerm(term)}
            onCreated={select}
            onClose={() => setCreateOpen(false)}
        />
    ) : null;

    if (value && !changing) {
        return (
            <div className="space-y-1">
                <p className="text-sm font-medium text-slate-700">Cliente</p>
                <div
                    data-testid="customer-picker-selected"
                    className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
                >
                    <div className="min-w-0">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Cliente seleccionado</p>
                        {needsDetail && detailQuery.isLoading ? (
                            <p className="text-sm text-slate-500">Cargando cliente...</p>
                        ) : (
                            <>
                                <p className="truncate text-sm font-semibold text-slate-900">
                                    {shown?.name ?? 'Cliente vinculado'}
                                    {shown?.is_active === false ? (
                                        <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">Dado de baja</span>
                                    ) : null}
                                </p>
                                <p className="truncate text-xs text-slate-500">{shown?.phone || 'Sin teléfono'}</p>
                            </>
                        )}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                        <a
                            href={`/app/clientes/${value.id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="rounded-full px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-white hover:text-slate-900"
                        >
                            Ver ficha
                        </a>
                        <button
                            type="button"
                            onClick={() => setChanging(true)}
                            className="rounded-full border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900"
                        >
                            Cambiar
                        </button>
                    </div>
                </div>
                {error ? <span className="block text-xs text-rose-600" role="alert">{error}</span> : null}
            </div>
        );
    }

    return (
        <div className="space-y-2">
            <label className="block text-sm font-medium text-slate-700">
                Cliente
                <input
                    type="search"
                    value={term}
                    onChange={(event) => setTerm(event.target.value)}
                    placeholder="Buscar cliente por nombre, teléfono o email..."
                    autoComplete="off"
                    className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                />
            </label>

            {term.trim().length < CUSTOMER_PICKER_MIN_CHARS ? (
                <p className="text-xs text-slate-500">
                    {value
                        ? 'Buscá otro cliente o mantené el actual.'
                        : emptyHint ?? 'Escribí al menos 2 caracteres. Si no elegís un cliente, se busca o crea por teléfono al guardar.'}
                </p>
            ) : pending || searchQuery.isLoading ? (
                <p className="text-xs text-slate-500" role="status">
                    Buscando clientes...
                </p>
            ) : searchQuery.isError ? (
                <p className="text-xs text-rose-600" role="alert">
                    No pudimos buscar clientes.{' '}
                    <button type="button" onClick={() => searchQuery.refetch()} className="font-semibold underline">
                        Reintentar
                    </button>
                </p>
            ) : (
                <div className="overflow-hidden rounded-xl border border-slate-200">
                    {results.length === 0 ? (
                        <p className="px-3 py-2 text-xs text-slate-500">No encontramos clientes con &quot;{debouncedTerm}&quot;.</p>
                    ) : (
                        <ul aria-label="Resultados de clientes" className="max-h-60 divide-y divide-slate-100 overflow-y-auto">
                            {results.map((customer) => (
                                <li key={customer.id}>
                                    <button
                                        type="button"
                                        onClick={() => select(customer)}
                                        className="block w-full px-3 py-2 text-left hover:bg-slate-50 focus:bg-slate-50 focus:outline-none"
                                    >
                                        <span className="block truncate text-sm font-semibold text-slate-900">{customer.name}</span>
                                        <span className="block truncate text-xs text-slate-500">
                                            {[customer.phone, customer.email].filter(Boolean).join(' · ') || 'Sin contacto'}
                                        </span>
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                    {canCreate ? (
                        <button
                            type="button"
                            onClick={() => setCreateOpen(true)}
                            className="block w-full border-t border-slate-100 px-3 py-2 text-left text-sm font-semibold text-slate-900 hover:bg-slate-50"
                        >
                            + Crear nuevo cliente
                        </button>
                    ) : null}
                </div>
            )}

            {value ? (
                <button
                    type="button"
                    onClick={() => {
                        setChanging(false);
                        setTerm('');
                    }}
                    className="text-xs font-semibold text-slate-600 underline hover:text-slate-900"
                >
                    Mantener cliente actual
                </button>
            ) : null}
            {error ? <span className="block text-xs text-rose-600" role="alert">{error}</span> : null}
            {createModal}
        </div>
    );
}

/** Lo tipeado precarga el alta: teléfono si son dígitos, email si tiene @, si no nombre. */
export function initialValuesFromTerm(rawTerm: string): { name?: string; phone?: string; email?: string } {
    const term = rawTerm.trim();
    if (!term) return {};
    if (term.includes('@')) return { email: term };
    if (/^[+\d][\d\s().-]*$/.test(term)) return { phone: term };
    return { name: term };
}
