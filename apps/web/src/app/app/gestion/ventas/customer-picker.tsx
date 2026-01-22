"use client";

import { useEffect, useMemo, useState } from 'react';

import { Modal } from '@/components/ui/modal';
import { CustomerFormFields } from '@/features/customers/components/customer-form-fields';
import { useCreateCustomer, useCustomers } from '@/features/customers/hooks';
import type { CustomerPayload, CustomerSummary } from '@/features/customers/types';
import { ApiError } from '@/lib/api/client';

const compactDefaults: CustomerPayload = {
    name: '',
    type: 'individual',
    doc_type: 'dni',
    country: 'Argentina',
};

type CustomerPickerProps = {
    value: CustomerSummary | null;
    onChange: (customer: CustomerSummary | null) => void;
};

export function CustomerPicker({ value, onChange }: CustomerPickerProps) {
    const [search, setSearch] = useState('');
    const [debouncedSearch, setDebouncedSearch] = useState('');
    const [showModal, setShowModal] = useState(false);
    const [form, setForm] = useState<CustomerPayload>(compactDefaults);
    const [formError, setFormError] = useState<string | null>(null);

    useEffect(() => {
        const handle = setTimeout(() => setDebouncedSearch(search.trim()), 300);
        return () => clearTimeout(handle);
    }, [search]);

    const customersQuery = useCustomers({ search: debouncedSearch || undefined, limit: 8 });
    const createCustomer = useCreateCustomer();

    const suggestions = useMemo(() => customersQuery.data?.results ?? [], [customersQuery.data]);

    const handleSelect = (customer: CustomerSummary) => {
        onChange(customer);
        setSearch('');
    };

    const handleModalClose = () => {
        if (createCustomer.isPending) {
            return;
        }
        setShowModal(false);
        setForm(compactDefaults);
        setFormError(null);
    };

    const handleFormChange = (field: keyof CustomerPayload, value: string | boolean | undefined) => {
        setForm((prev) => ({
            ...prev,
            [field]: typeof value === 'string' ? value : value ?? prev[field],
        }));
    };

    const handleCreate = async () => {
        if (!form.name.trim()) {
            setFormError('Ingresá al menos el nombre del cliente.');
            return;
        }
        setFormError(null);
        try {
            const payload: CustomerPayload = {
                ...form,
                name: form.name.trim(),
            };
            const customer = await createCustomer.mutateAsync(payload);
            handleSelect(toSummary(customer));
            setForm(compactDefaults);
            setShowModal(false);
        } catch (error) {
            if (error instanceof ApiError) {
                const detail = (error.payload as Record<string, string[] | string> | undefined)?.detail;
                if (typeof detail === 'string') {
                    setFormError(detail);
                    return;
                }
                const firstFieldMessage = Object.values(error.payload as Record<string, string[]>)[0]?.[0];
                if (firstFieldMessage) {
                    setFormError(firstFieldMessage);
                    return;
                }
            }
            setFormError('No pudimos crear el cliente. Intentá nuevamente.');
        }
    };

    return (
        <section className="space-y-4 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Cliente</p>
                    <h2 className="text-xl font-semibold text-slate-900">Asigná la venta a un cliente</h2>
                    <p className="text-sm text-slate-500">El nombre es obligatorio para nuevos registros.</p>
                </div>
                <button
                    type="button"
                    onClick={() => setShowModal(true)}
                    className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-900 hover:text-slate-900"
                >
                    + Nuevo cliente
                </button>
            </div>
            {value ? (
                <div className="flex flex-col gap-3 rounded-2xl border border-slate-100 bg-slate-50 p-4 md:flex-row md:items-center md:justify-between">
                    <div>
                        <p className="text-sm text-slate-500">Cliente seleccionado</p>
                        <p className="text-lg font-semibold text-slate-900">{value.name}</p>
                        <p className="text-sm text-slate-500">
                            {value.doc_number ? `${value.doc_type?.toUpperCase() ?? ''} ${value.doc_number}` : value.email || value.phone || 'Sin datos adicionales'}
                        </p>
                    </div>
                    <div className="flex flex-col gap-2 text-sm font-semibold text-slate-700 md:flex-row">
                        <button
                            type="button"
                            onClick={() => onChange(null)}
                            className="rounded-full border border-slate-200 px-4 py-2 hover:border-slate-900 hover:text-slate-900"
                        >
                            Cambiar cliente
                        </button>
                    </div>
                </div>
            ) : (
                <div className="space-y-3">
                    <label className="text-sm font-semibold text-slate-700">
                        Buscar cliente existente
                        <input
                            type="search"
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                            placeholder="Nombre, documento, email o teléfono"
                            className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                    </label>
                    <div className="rounded-2xl border border-dashed border-slate-200">
                        {customersQuery.isLoading ? (
                            <p className="p-4 text-sm text-slate-500">Buscando clientes...</p>
                        ) : suggestions.length === 0 ? (
                            <p className="p-4 text-sm text-slate-500">No encontramos clientes con ese término.</p>
                        ) : (
                            <ul className="divide-y divide-slate-100">
                                {suggestions.map((customer) => (
                                    <li key={customer.id} className="flex items-center justify-between px-4 py-3">
                                        <div>
                                            <p className="font-medium text-slate-900">{customer.name}</p>
                                            <p className="text-xs text-slate-500">
                                                {customer.doc_number ? `${customer.doc_type?.toUpperCase() ?? ''} ${customer.doc_number}` : customer.email || customer.phone || 'Sin datos adicionales'}
                                            </p>
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => handleSelect(toSummary(customer))}
                                            className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 transition hover:border-slate-900 hover:text-slate-900"
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
            <Modal open={showModal} title="Nuevo cliente" onClose={handleModalClose}>
                <CustomerFormFields form={form} onChange={handleFormChange} showAddress={false} />
                {formError ? <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">{formError}</p> : null}
                <div className="flex items-center justify-end gap-3 pt-2">
                    <button
                        type="button"
                        onClick={handleModalClose}
                        className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                    >
                        Cancelar
                    </button>
                    <button
                        type="button"
                        onClick={handleCreate}
                        disabled={createCustomer.isPending}
                        className="rounded-full border border-slate-900 bg-slate-900 px-5 py-2 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-200"
                    >
                        {createCustomer.isPending ? 'Guardando...' : 'Guardar cliente'}
                    </button>
                </div>
            </Modal>
        </section>
    );
}

function toSummary(customer: CustomerSummary): CustomerSummary {
    return {
        id: customer.id,
        name: customer.name,
        doc_type: customer.doc_type ?? null,
        doc_number: customer.doc_number ?? null,
        email: customer.email ?? null,
        phone: customer.phone ?? null,
    };
}
