"use client";

import { useEffect, useMemo, useState } from 'react';

import { Modal } from '@/components/ui/modal';
import { CustomerFormFields } from '@/features/customers/components/customer-form-fields';
import { useCreateCustomer, useCustomers, useUpdateCustomer } from '@/features/customers/hooks';
import type { Customer, CustomerPayload } from '@/features/customers/types';
import { ApiError } from '@/lib/api/client';

const initialPayload: CustomerPayload = {
    name: '',
    type: 'individual',
    doc_type: 'dni',
    tax_condition: 'consumer',
    country: 'Argentina',
};

type CustomersClientProps = {
    canCreate: boolean;
    canManage: boolean;
};

export function CustomersClient({ canCreate, canManage }: CustomersClientProps) {
    const [search, setSearch] = useState('');
    const [includeInactive, setIncludeInactive] = useState(false);
    const [debouncedSearch, setDebouncedSearch] = useState('');
    const [modalOpen, setModalOpen] = useState(false);
    const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
    const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
    const [form, setForm] = useState<CustomerPayload>(initialPayload);
    const [formError, setFormError] = useState<string | null>(null);

    useEffect(() => {
        const timeout = setTimeout(() => setDebouncedSearch(search.trim()), 300);
        return () => clearTimeout(timeout);
    }, [search]);

    const customersQuery = useCustomers({ search: debouncedSearch || undefined, includeInactive, limit: 50 });
    const createMutation = useCreateCustomer();
    const updateMutation = useUpdateCustomer();

    const customers = useMemo(() => customersQuery.data?.results ?? [], [customersQuery.data]);

    const openCreateModal = () => {
        setModalMode('create');
        setSelectedCustomer(null);
        setForm(initialPayload);
        setFormError(null);
        setModalOpen(true);
    };

    const openEditModal = (customer: Customer) => {
        setModalMode('edit');
        setSelectedCustomer(customer);
        setForm(toPayload(customer));
        setFormError(null);
        setModalOpen(true);
    };

    const closeModal = () => {
        if (createMutation.isPending || updateMutation.isPending) {
            return;
        }
        setModalOpen(false);
    };

    const handleFormChange = (field: keyof CustomerPayload, value: string | boolean | undefined) => {
        setForm((prev) => ({
            ...prev,
            [field]: typeof value === 'string' ? value : value ?? prev[field],
        }));
    };

    const handleSave = async () => {
        if (!form.name.trim()) {
            setFormError('Ingresá el nombre del cliente.');
            return;
        }
        setFormError(null);
        const payload: CustomerPayload = {
            ...form,
            name: form.name.trim(),
        };
        try {
            if (modalMode === 'create') {
                if (!canCreate) {
                    setFormError('No tenés permiso para crear clientes.');
                    return;
                }
                await createMutation.mutateAsync(payload);
            } else if (selectedCustomer) {
                if (!canManage) {
                    setFormError('No tenés permiso para editar clientes.');
                    return;
                }
                await updateMutation.mutateAsync({ id: selectedCustomer.id, payload });
            }
            setModalOpen(false);
            setSelectedCustomer(null);
            setForm(initialPayload);
        } catch (error) {
            setFormError(resolveApiError(error));
        }
    };

    const handleToggleActive = async (customer: Customer) => {
        if (!canManage) {
            return;
        }
        try {
            await updateMutation.mutateAsync({ id: customer.id, payload: { is_active: !customer.is_active } });
        } catch (error) {
            setFormError(resolveApiError(error));
        }
    };

    return (
        <section className="space-y-4">
            <header className="flex flex-col gap-3 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm md:flex-row md:items-center md:justify-between">
                <div>
                    <h2 className="text-2xl font-semibold text-slate-900">Clientes</h2>
                    <p className="text-sm text-slate-500">Gestioná la agenda de clientes para vincular ventas e informes.</p>
                </div>
                {canCreate ? (
                    <button
                        type="button"
                        onClick={openCreateModal}
                        className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-800"
                    >
                        Nuevo cliente
                    </button>
                ) : null}
            </header>
            <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="grid gap-3 md:grid-cols-4">
                    <input
                        type="search"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        placeholder="Buscar por nombre, email o documento"
                        className="rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none md:col-span-3"
                    />
                    <label className="flex items-center gap-2 rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600">
                        <input
                            type="checkbox"
                            checked={includeInactive}
                            onChange={(event) => setIncludeInactive(event.target.checked)}
                            className="rounded border-slate-300 text-slate-900 focus:ring-slate-900"
                        />
                        Incluir inactivos
                    </label>
                </div>
                <p className="mt-3 text-xs uppercase tracking-wide text-slate-400">{customersQuery.data?.count ?? 0} registros</p>
                <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Nombre</th>
                                <th className="px-3 py-2">Contacto</th>
                                <th className="px-3 py-2">Estado</th>
                                <th className="px-3 py-2 text-right">Acciones</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {customersQuery.isLoading ? (
                                <tr>
                                    <td colSpan={4} className="px-3 py-6 text-center text-slate-500">
                                        Cargando clientes...
                                    </td>
                                </tr>
                            ) : customers.length === 0 ? (
                                <tr>
                                    <td colSpan={4} className="px-3 py-6 text-center text-slate-500">
                                        No se encontraron clientes.
                                    </td>
                                </tr>
                            ) : (
                                customers.map((customer) => (
                                    <tr key={customer.id}>
                                        <td className="px-3 py-3">
                                            <p className="font-semibold text-slate-900">{customer.name}</p>
                                            {customer.doc_number ? (
                                                <p className="text-xs text-slate-500">
                                                    {customer.doc_type?.toUpperCase() ?? ''} {customer.doc_number}
                                                </p>
                                            ) : null}
                                        </td>
                                        <td className="px-3 py-3 text-slate-600">
                                            {customer.email || 'Sin email'}
                                            <br />
                                            {customer.phone || 'Sin teléfono'}
                                        </td>
                                        <td className="px-3 py-3">
                                            <span
                                                className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${customer.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'
                                                    }`}
                                            >
                                                {customer.is_active ? 'Activo' : 'Inactivo'}
                                            </span>
                                        </td>
                                        <td className="px-3 py-3 text-right text-sm font-semibold text-slate-600">
                                            <div className="flex flex-col gap-2 md:flex-row md:justify-end">
                                                {canManage ? (
                                                    <button
                                                        type="button"
                                                        onClick={() => openEditModal(customer)}
                                                        className="text-slate-600 hover:text-slate-900"
                                                    >
                                                        Editar
                                                    </button>
                                                ) : null}
                                                {canManage ? (
                                                    <button
                                                        type="button"
                                                        onClick={() => handleToggleActive(customer)}
                                                        className="text-slate-600 hover:text-slate-900"
                                                    >
                                                        {customer.is_active ? 'Desactivar' : 'Activar'}
                                                    </button>
                                                ) : null}
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
            <Modal
                open={modalOpen}
                title={modalMode === 'create' ? 'Nuevo cliente' : 'Editar cliente'}
                onClose={closeModal}
            >
                <CustomerFormFields form={form} onChange={handleFormChange} />
                {formError ? <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">{formError}</p> : null}
                <div className="flex items-center justify-end gap-3 pt-2">
                    <button
                        type="button"
                        onClick={closeModal}
                        className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                    >
                        Cancelar
                    </button>
                    <button
                        type="button"
                        disabled={(modalMode === 'create' ? createMutation.isPending : updateMutation.isPending) || (!canCreate && modalMode === 'create')}
                        onClick={handleSave}
                        className="rounded-full border border-slate-900 bg-slate-900 px-5 py-2 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-200"
                    >
                        {modalMode === 'create'
                            ? createMutation.isPending
                                ? 'Guardando...'
                                : 'Crear cliente'
                            : updateMutation.isPending
                                ? 'Guardando...'
                                : 'Guardar cambios'}
                    </button>
                </div>
            </Modal>
        </section>
    );
}

function toPayload(customer: Customer): CustomerPayload {
    return {
        name: customer.name,
        type: customer.type,
        doc_type: customer.doc_type ?? undefined,
        doc_number: customer.doc_number ?? undefined,
        tax_condition: customer.tax_condition ?? undefined,
        email: customer.email ?? undefined,
        phone: customer.phone ?? undefined,
        address_line: customer.address_line ?? undefined,
        city: customer.city ?? undefined,
        province: customer.province ?? undefined,
        postal_code: customer.postal_code ?? undefined,
        country: customer.country ?? undefined,
        note: customer.note ?? undefined,
        is_active: customer.is_active,
    };
}

function resolveApiError(error: unknown) {
    if (error instanceof ApiError) {
        const payload = error.payload as Record<string, string[] | string> | undefined;
        if (payload) {
            if (typeof payload.detail === 'string') {
                return payload.detail;
            }
            const first = Object.values(payload).find((value) => Array.isArray(value) && value.length > 0);
            if (first && Array.isArray(first)) {
                return first[0];
            }
        }
    }
    return 'No pudimos guardar el cliente. Intentá nuevamente.';
}
