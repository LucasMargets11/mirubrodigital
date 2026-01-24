"use client";

import { type FormEvent, useEffect, useMemo, useState } from 'react';

import { useCreateCustomer, useCustomers } from '@/features/customers/hooks';
import type { Customer, CustomerPayload, CustomerSummary } from '@/features/customers/types';
import { ApiError } from '@/lib/api/client';

const MIN_NAME_LENGTH = 2;

const quickDefaults: Pick<CustomerPayload, 'type' | 'doc_type' | 'country'> = {
    type: 'individual',
    doc_type: 'dni',
    country: 'Argentina',
};

const newCustomerDefaults = {
    name: '',
    doc_number: '',
    phone: '',
    email: '',
};

type CustomerMode = 'quick' | 'new' | 'existing';

const modeLabels: Record<CustomerMode, string> = {
    quick: 'Solo nombre',
    new: 'Nuevo cliente',
    existing: 'Cliente existente',
};

type SaleCustomerPickerProps = {
    value: CustomerSummary | null;
    onChange: (customer: CustomerSummary | null) => void;
};

export function SaleCustomerPicker({ value, onChange }: SaleCustomerPickerProps) {
    const [activeMode, setActiveMode] = useState<CustomerMode>('quick');
    const [lastSelectionMode, setLastSelectionMode] = useState<CustomerMode | null>(null);
    const [quickName, setQuickName] = useState('');
    const [quickError, setQuickError] = useState<string | null>(null);
    const [newForm, setNewForm] = useState(() => ({ ...newCustomerDefaults }));
    const [newFormError, setNewFormError] = useState<string | null>(null);
    const [search, setSearch] = useState('');
    const [debouncedSearch, setDebouncedSearch] = useState('');
    const [pendingMode, setPendingMode] = useState<CustomerMode | null>(null);

    useEffect(() => {
        const handle = setTimeout(() => setDebouncedSearch(search.trim()), 300);
        return () => clearTimeout(handle);
    }, [search]);

    const shouldQueryCustomers = debouncedSearch.length >= 2;

    const customersQuery = useCustomers(
        { search: shouldQueryCustomers ? debouncedSearch : undefined, limit: 15 },
        { enabled: shouldQueryCustomers }
    );
    const suggestions = useMemo(() => customersQuery.data?.results ?? [], [customersQuery.data]);

    const createCustomer = useCreateCustomer();

    const handleSelect = (customer: CustomerSummary, mode: CustomerMode) => {
        onChange(customer);
        setLastSelectionMode(mode);
    };

    const resetSelection = () => {
        onChange(null);
        setActiveMode(lastSelectionMode ?? 'quick');
    };

    const handleQuickSubmit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const trimmed = quickName.trim();
        if (trimmed.length < MIN_NAME_LENGTH) {
            setQuickError('Ingresá al menos 2 caracteres.');
            return;
        }
        setQuickError(null);
        try {
            setPendingMode('quick');
            const customer = await createCustomer.mutateAsync({
                ...quickDefaults,
                name: trimmed,
            });
            handleSelect(toSummary(customer), 'quick');
            setQuickName('');
        } catch (error) {
            setQuickError(resolveCustomerError(error));
        } finally {
            setPendingMode(null);
        }
    };

    const handleNewSubmit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const trimmed = newForm.name.trim();
        if (trimmed.length < MIN_NAME_LENGTH) {
            setNewFormError('Ingresá el nombre del cliente.');
            return;
        }
        setNewFormError(null);
        try {
            setPendingMode('new');
            const payload: CustomerPayload = {
                ...quickDefaults,
                name: trimmed,
            };
            if (newForm.doc_number.trim()) {
                payload.doc_number = newForm.doc_number.trim();
            }
            if (newForm.phone.trim()) {
                payload.phone = newForm.phone.trim();
            }
            if (newForm.email.trim()) {
                payload.email = newForm.email.trim();
            }
            const customer = await createCustomer.mutateAsync(payload);
            handleSelect(toSummary(customer), 'new');
            setNewForm({ ...newCustomerDefaults });
        } catch (error) {
            setNewFormError(resolveCustomerError(error));
        } finally {
            setPendingMode(null);
        }
    };

    const handleExistingSelect = (customer: Customer) => {
        handleSelect(toSummary(customer), 'existing');
        setSearch('');
    };

    const isSubmittingQuick = pendingMode === 'quick' && createCustomer.isPending;
    const isSubmittingNew = pendingMode === 'new' && createCustomer.isPending;

    return (
        <section className="space-y-4 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Cliente</p>
                    <h2 className="text-xl font-semibold text-slate-900">Elegí cómo asociar la venta</h2>
                    <p className="text-sm text-slate-500">Seleccioná un modo para continuar con los productos.</p>
                </div>
                {value ? (
                    <button
                        type="button"
                        onClick={resetSelection}
                        className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-900 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900"
                    >
                        Cambiar cliente
                    </button>
                ) : null}
            </header>
            {value ? (
                <div className="flex flex-col gap-3 rounded-2xl border border-slate-100 bg-slate-50 p-4 md:flex-row md:items-center md:justify-between">
                    <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                            Cliente seleccionado {lastSelectionMode ? `(${modeLabels[lastSelectionMode]})` : ''}
                        </p>
                        <p className="text-lg font-semibold text-slate-900">{value.name}</p>
                        <p className="text-sm text-slate-500">
                            {value.doc_number
                                ? `${value.doc_type?.toUpperCase() ?? ''} ${value.doc_number}`.trim()
                                : value.email || value.phone || 'Sin datos adicionales'}
                        </p>
                    </div>
                    <p className="text-sm text-slate-500">La selección se puede editar antes de confirmar.</p>
                </div>
            ) : (
                <div className="space-y-5">
                    <div className="grid gap-3 lg:grid-cols-3">
                        {(['quick', 'new', 'existing'] as CustomerMode[]).map((mode) => (
                            <label
                                key={mode}
                                className={`relative flex cursor-pointer flex-col rounded-2xl border px-4 py-3 transition focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-slate-900 ${activeMode === mode ? 'border-slate-900 bg-slate-50' : 'border-slate-200 bg-white hover:border-slate-300'
                                    }`}
                            >
                                <input
                                    type="radio"
                                    name="customer-mode"
                                    value={mode}
                                    checked={activeMode === mode}
                                    onChange={() => setActiveMode(mode)}
                                    className="sr-only"
                                    aria-label={`Elegir opción ${modeLabels[mode]}`}
                                />
                                <span className="text-sm font-semibold text-slate-900">{modeLabels[mode]}</span>
                                <span className="text-xs text-slate-500">
                                    {mode === 'quick' && 'Ingresá solo el nombre y seguí.'}
                                    {mode === 'new' && 'Creá un cliente con los datos básicos.'}
                                    {mode === 'existing' && 'Buscá entre tus clientes registrados.'}
                                </span>
                            </label>
                        ))}
                    </div>
                    {activeMode === 'quick' && (
                        <form onSubmit={handleQuickSubmit} className="space-y-3" aria-label="Crear cliente rápido">
                            <label className="text-sm font-semibold text-slate-700">
                                Nombre del cliente
                                <input
                                    type="text"
                                    value={quickName}
                                    onChange={(event) => setQuickName(event.target.value)}
                                    minLength={MIN_NAME_LENGTH}
                                    required
                                    placeholder="Ej. Consumidor final"
                                    className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                />
                            </label>
                            {quickError ? <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">{quickError}</p> : null}
                            <button
                                type="submit"
                                disabled={isSubmittingQuick}
                                className="inline-flex items-center justify-center rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                            >
                                {isSubmittingQuick ? 'Guardando...' : 'Continuar'}
                            </button>
                        </form>
                    )}
                    {activeMode === 'new' && (
                        <form onSubmit={handleNewSubmit} className="space-y-3" aria-label="Crear nuevo cliente">
                            <div className="grid gap-3 md:grid-cols-2">
                                <label className="text-sm font-semibold text-slate-700 md:col-span-2">
                                    Nombre completo
                                    <input
                                        type="text"
                                        value={newForm.name}
                                        onChange={(event) => setNewForm((prev) => ({ ...prev, name: event.target.value }))}
                                        minLength={MIN_NAME_LENGTH}
                                        required
                                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                    />
                                </label>
                                <label className="text-sm font-semibold text-slate-700">
                                    Documento (opcional)
                                    <input
                                        type="text"
                                        value={newForm.doc_number}
                                        onChange={(event) => setNewForm((prev) => ({ ...prev, doc_number: event.target.value }))}
                                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                        placeholder="DNI / CUIT"
                                    />
                                </label>
                                <label className="text-sm font-semibold text-slate-700">
                                    Teléfono (opcional)
                                    <input
                                        type="tel"
                                        value={newForm.phone}
                                        onChange={(event) => setNewForm((prev) => ({ ...prev, phone: event.target.value }))}
                                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                        placeholder="Ej. +54 11 5555 0000"
                                    />
                                </label>
                                <label className="text-sm font-semibold text-slate-700 md:col-span-2">
                                    Email (opcional)
                                    <input
                                        type="email"
                                        value={newForm.email}
                                        onChange={(event) => setNewForm((prev) => ({ ...prev, email: event.target.value }))}
                                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                        placeholder="cliente@negocio.com"
                                    />
                                </label>
                            </div>
                            {newFormError ? <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">{newFormError}</p> : null}
                            <div className="flex flex-wrap items-center gap-3">
                                <button
                                    type="submit"
                                    disabled={isSubmittingNew}
                                    className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                                >
                                    {isSubmittingNew ? 'Creando...' : 'Crear y continuar'}
                                </button>
                                <p className="text-xs text-slate-500">Se guardará con los datos ingresados.</p>
                            </div>
                        </form>
                    )}
                    {activeMode === 'existing' && (
                        <div className="space-y-3" aria-label="Buscar cliente existente">
                            <label className="text-sm font-semibold text-slate-700">
                                Buscar por nombre, documento, email o teléfono
                                <input
                                    type="search"
                                    value={search}
                                    onChange={(event) => setSearch(event.target.value)}
                                    placeholder="Escribí al menos 2 caracteres"
                                    className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                />
                            </label>
                            <div className="rounded-2xl border border-dashed border-slate-200">
                                {!shouldQueryCustomers ? (
                                    <p className="p-4 text-sm text-slate-500">Escribí para buscar en tu lista de clientes.</p>
                                ) : customersQuery.isLoading ? (
                                    <p className="p-4 text-sm text-slate-500">Buscando clientes...</p>
                                ) : suggestions.length === 0 ? (
                                    <p className="p-4 text-sm text-slate-500">No encontramos resultados con ese término.</p>
                                ) : (
                                    <ul className="divide-y divide-slate-100" role="listbox">
                                        {suggestions.slice(0, 15).map((customer) => (
                                            <li key={customer.id} className="flex items-center justify-between px-4 py-3">
                                                <div>
                                                    <p className="font-medium text-slate-900">{customer.name}</p>
                                                    <p className="text-xs text-slate-500">
                                                        {customer.doc_number
                                                            ? `${customer.doc_type?.toUpperCase() ?? ''} ${customer.doc_number}`.trim()
                                                            : customer.email || customer.phone || 'Sin datos adicionales'}
                                                    </p>
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => handleExistingSelect(customer)}
                                                    className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 transition hover:border-slate-900 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900"
                                                >
                                                    Seleccionar
                                                </button>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </section>
    );
}

function resolveCustomerError(error: unknown) {
    if (error instanceof ApiError) {
        const payload = error.payload as Record<string, string[] | string> | undefined;
        if (!payload) {
            return 'No pudimos guardar el cliente. Intentá nuevamente.';
        }
        if (typeof payload.detail === 'string') {
            return payload.detail;
        }
        const firstField = Object.values(payload).find((message) => typeof message === 'string' || Array.isArray(message));
        if (typeof firstField === 'string') {
            return firstField;
        }
        if (Array.isArray(firstField) && firstField.length > 0) {
            return firstField[0];
        }
    }
    return 'No pudimos guardar el cliente. Intentá nuevamente.';
}

function toSummary(customer: Customer | CustomerSummary): CustomerSummary {
    return {
        id: customer.id,
        name: customer.name,
        doc_type: customer.doc_type ?? null,
        doc_number: customer.doc_number ?? null,
        email: customer.email ?? null,
        phone: customer.phone ?? null,
    };
}
