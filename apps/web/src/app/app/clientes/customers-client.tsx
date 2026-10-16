"use client";

import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

import { CustomerFormModal, resolveCustomerApiError } from '@/features/customers/components/customer-form-modal';
import { useCustomers, useUpdateCustomer } from '@/features/customers/hooks';
import type { Customer } from '@/features/customers/types';

type CustomersClientProps = {
    canCreate: boolean;
    canManage: boolean;
};

export function CustomersClient({ canCreate, canManage }: CustomersClientProps) {
    const router = useRouter();
    const [search, setSearch] = useState('');
    const [includeInactive, setIncludeInactive] = useState(false);
    const [debouncedSearch, setDebouncedSearch] = useState('');
    const [modalOpen, setModalOpen] = useState(false);
    const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
    const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
    const [actionError, setActionError] = useState<string | null>(null);

    useEffect(() => {
        const timeout = setTimeout(() => setDebouncedSearch(search.trim()), 300);
        return () => clearTimeout(timeout);
    }, [search]);

    const customersQuery = useCustomers({ search: debouncedSearch || undefined, includeInactive, limit: 50 });
    const updateMutation = useUpdateCustomer();

    const customers = useMemo(() => customersQuery.data?.results ?? [], [customersQuery.data]);

    const openCreateModal = () => {
        setModalMode('create');
        setSelectedCustomer(null);
        setModalOpen(true);
    };

    const openEditModal = (customer: Customer) => {
        setModalMode('edit');
        setSelectedCustomer(customer);
        setModalOpen(true);
    };

    const closeModal = () => {
        setModalOpen(false);
        setSelectedCustomer(null);
    };

    const handleToggleActive = async (customer: Customer) => {
        if (!canManage) {
            return;
        }
        try {
            setActionError(null);
            await updateMutation.mutateAsync({ id: customer.id, payload: { is_active: !customer.is_active } });
        } catch (error) {
            setActionError(resolveCustomerApiError(error));
        }
    };

    return (
        <section className="space-y-4">
            <header className="flex flex-col gap-3 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm md:flex-row md:items-center md:justify-between">
                <div>
                    <h2 className="text-2xl font-semibold text-slate-900">Clientes</h2>
                    <p className="text-sm text-slate-500">El padrón de clientes de tu negocio, compartido entre tus servicios.</p>
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
                {actionError ? (
                    <p role="alert" className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                        {actionError}
                    </p>
                ) : null}
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
                                    <tr
                                        key={customer.id}
                                        onClick={() => router.push(`/app/clientes/${customer.id}` as any)}
                                        className="cursor-pointer hover:bg-slate-50"
                                    >
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
                                                        onClick={(e) => { e.stopPropagation(); openEditModal(customer); }}
                                                        className="text-slate-600 hover:text-slate-900"
                                                    >
                                                        Editar
                                                    </button>
                                                ) : null}
                                                {canManage ? (
                                                    <button
                                                        type="button"
                                                        onClick={(e) => { e.stopPropagation(); void handleToggleActive(customer); }}
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
            {modalOpen ? (
                <CustomerFormModal
                    mode={modalMode}
                    customer={selectedCustomer}
                    canSubmit={modalMode === 'create' ? canCreate : canManage}
                    onClose={closeModal}
                />
            ) : null}
        </section>
    );
}
