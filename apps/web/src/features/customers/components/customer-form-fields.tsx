"use client";

import type { CustomerPayload } from '../types';

const customerTypes: { value: CustomerPayload['type']; label: string }[] = [
    { value: 'individual', label: 'Persona' },
    { value: 'company', label: 'Empresa' },
];

const documentTypes = [
    { value: '', label: 'Sin documento' },
    { value: 'dni', label: 'DNI' },
    { value: 'cuit', label: 'CUIT' },
    { value: 'passport', label: 'Pasaporte' },
    { value: 'other', label: 'Otro' },
];

const taxConditions = [
    { value: '', label: 'Sin condición' },
    { value: 'consumer', label: 'Consumidor Final' },
    { value: 'monotax', label: 'Monotributo' },
    { value: 'registered', label: 'Responsable Inscripto' },
    { value: 'exempt', label: 'Exento' },
    { value: 'other', label: 'Otro' },
];

type CustomerFormFieldsProps = {
    form: CustomerPayload;
    onChange: (field: keyof CustomerPayload, value: string | boolean | undefined) => void;
    showAddress?: boolean;
};

export function CustomerFormFields({ form, onChange, showAddress = true }: CustomerFormFieldsProps) {
    return (
        <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
                <label className="text-sm font-semibold text-slate-700">
                    Nombre <span className="text-rose-600" aria-hidden="true">*</span>
                    <span className="sr-only">Campo obligatorio</span>
                    <input
                        type="text"
                        value={form.name}
                        onChange={(event) => onChange('name', event.target.value)}
                        placeholder="Consumidor Final"
                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        required
                        aria-required="true"
                    />
                </label>
                <label className="text-sm font-semibold text-slate-700">
                    Tipo
                    <select
                        value={form.type ?? 'individual'}
                        onChange={(event) => onChange('type', event.target.value)}
                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                    >
                        {customerTypes.map((option) => (
                            <option key={option.value} value={option.value ?? ''}>
                                {option.label}
                            </option>
                        ))}
                    </select>
                </label>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
                <label className="text-sm font-semibold text-slate-700">
                    Tipo de documento
                    <select
                        value={form.doc_type ?? ''}
                        onChange={(event) => onChange('doc_type', event.target.value)}
                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                    >
                        {documentTypes.map((option) => (
                            <option key={option.value} value={option.value}>
                                {option.label}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="text-sm font-semibold text-slate-700">
                    Número de documento
                    <input
                        type="text"
                        value={form.doc_number ?? ''}
                        onChange={(event) => onChange('doc_number', event.target.value)}
                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                    />
                </label>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
                <label className="text-sm font-semibold text-slate-700">
                    Email
                    <input
                        type="email"
                        value={form.email ?? ''}
                        onChange={(event) => onChange('email', event.target.value)}
                        placeholder="cliente@ejemplo.com"
                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                    />
                </label>
                <label className="text-sm font-semibold text-slate-700">
                    Teléfono
                    <input
                        type="tel"
                        value={form.phone ?? ''}
                        onChange={(event) => onChange('phone', event.target.value)}
                        placeholder="+54 9 ..."
                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                    />
                </label>
            </div>
            {showAddress ? (
                <div className="space-y-4">
                    <label className="text-sm font-semibold text-slate-700">
                        Dirección
                        <input
                            type="text"
                            value={form.address_line ?? ''}
                            onChange={(event) => onChange('address_line', event.target.value)}
                            placeholder="Calle 123"
                            className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                    </label>
                    <div className="grid gap-4 sm:grid-cols-3">
                        <label className="text-sm font-semibold text-slate-700">
                            Ciudad
                            <input
                                type="text"
                                value={form.city ?? ''}
                                onChange={(event) => onChange('city', event.target.value)}
                                className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            />
                        </label>
                        <label className="text-sm font-semibold text-slate-700">
                            Provincia
                            <input
                                type="text"
                                value={form.province ?? ''}
                                onChange={(event) => onChange('province', event.target.value)}
                                className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            />
                        </label>
                        <label className="text-sm font-semibold text-slate-700">
                            Código postal
                            <input
                                type="text"
                                value={form.postal_code ?? ''}
                                onChange={(event) => onChange('postal_code', event.target.value)}
                                className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            />
                        </label>
                    </div>
                    <label className="text-sm font-semibold text-slate-700">
                        País
                        <input
                            type="text"
                            value={form.country ?? ''}
                            onChange={(event) => onChange('country', event.target.value)}
                            className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                    </label>
                </div>
            ) : null}
            <label className="text-sm font-semibold text-slate-700">
                Condición fiscal
                <select
                    value={form.tax_condition ?? ''}
                    onChange={(event) => onChange('tax_condition', event.target.value)}
                    className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                >
                    {taxConditions.map((option) => (
                        <option key={option.value} value={option.value}>
                            {option.label}
                        </option>
                    ))}
                </select>
            </label>
            <label className="text-sm font-semibold text-slate-700">
                Notas
                <textarea
                    value={form.note ?? ''}
                    onChange={(event) => onChange('note', event.target.value)}
                    rows={showAddress ? 3 : 2}
                    className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                />
            </label>
        </div>
    );
}
