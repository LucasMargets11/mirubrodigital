'use client';

import { useState } from 'react';

import { Modal } from '@/components/ui/modal';
import { ApiError } from '@/lib/api/client';

import { useCreateCustomer, useUpdateCustomer } from '../hooks';
import type { Customer, CustomerPayload } from '../types';
import { CustomerFormFields } from './customer-form-fields';

const initialPayload: CustomerPayload = {
    name: '',
    type: 'individual',
    doc_type: 'dni',
    tax_condition: 'consumer',
    country: 'Argentina',
};

type CustomerFormModalProps = {
    mode: 'create' | 'edit';
    /** Requerido en modo `edit`: precarga el formulario. */
    customer?: Customer | null;
    /** Permiso para la acción del modo (crear o `manage_customers`). El backend valida igual. */
    canSubmit: boolean;
    onClose: () => void;
    /** Solo `create`: valores iniciales (p.ej. lo tipeado en el CustomerPicker de Turnos, CUSTOMER 05). */
    initialValues?: Partial<CustomerPayload>;
    /** Solo `create`: recibe el Customer creado antes de cerrar (el picker lo selecciona). */
    onCreated?: (customer: Customer) => void;
};

/**
 * Modal de alta/edición de Customer compartido por el listado y la ficha
 * (CUSTOMER 02B). Se monta solo mientras está abierto: cada apertura arranca
 * con los datos actuales y cancelar descarta lo tipeado. Tras guardar, el hook
 * invalida `['gestion', 'customers']` (listado y ficha se re-fetchean).
 */
export function CustomerFormModal({ mode, customer, canSubmit, onClose, initialValues, onCreated }: CustomerFormModalProps) {
    const [form, setForm] = useState<CustomerPayload>(() =>
        mode === 'edit' && customer ? toPayload(customer) : { ...initialPayload, ...initialValues },
    );
    const [formError, setFormError] = useState<string | null>(null);

    const createMutation = useCreateCustomer();
    const updateMutation = useUpdateCustomer();
    const isPending = mode === 'create' ? createMutation.isPending : updateMutation.isPending;

    const closeModal = () => {
        if (createMutation.isPending || updateMutation.isPending) {
            return;
        }
        onClose();
    };

    const handleFormChange = (field: keyof CustomerPayload, value: string | boolean | undefined) => {
        setForm((prev) => ({
            ...prev,
            [field]: typeof value === 'string' ? value : (value ?? prev[field]),
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
            if (mode === 'create') {
                if (!canSubmit) {
                    setFormError('No tenés permiso para crear clientes.');
                    return;
                }
                const created = await createMutation.mutateAsync(payload);
                onCreated?.(created);
            } else if (customer) {
                if (!canSubmit) {
                    setFormError('No tenés permiso para editar clientes.');
                    return;
                }
                await updateMutation.mutateAsync({ id: customer.id, payload });
            }
            onClose();
        } catch (error) {
            setFormError(resolveCustomerApiError(error));
        }
    };

    // El error vive en el footer fijo: siempre visible junto a Guardar, aunque el cuerpo esté scrolleado.
    const footer = (
        <div className="space-y-3">
            {formError ? (
                <p role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                    {formError}
                </p>
            ) : null}
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end sm:gap-3">
                <button
                    type="button"
                    onClick={closeModal}
                    className="rounded-full border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900 sm:py-2"
                >
                    Cancelar
                </button>
                <button
                    type="button"
                    disabled={isPending || (!canSubmit && mode === 'create')}
                    onClick={handleSave}
                    className="rounded-full border border-slate-900 bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-200 sm:py-2"
                >
                    {isPending ? 'Guardando...' : mode === 'create' ? 'Crear cliente' : 'Guardar cambios'}
                </button>
            </div>
        </div>
    );

    // Header y acciones fijos; solo los campos scrollean (CUSTOMER 03).
    return (
        <Modal open title={mode === 'create' ? 'Nuevo cliente' : 'Editar cliente'} onClose={closeModal} footer={footer}>
            <CustomerFormFields form={form} onChange={handleFormChange} />
        </Modal>
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

export function resolveCustomerApiError(error: unknown) {
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
