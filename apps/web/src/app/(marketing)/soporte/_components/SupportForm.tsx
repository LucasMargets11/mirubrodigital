'use client';

import { useState, useId } from 'react';
import { MessageSquare } from 'lucide-react';
import { PRODUCT_OPTIONS } from '../_constants';
import { buildSupportMessage, buildWhatsAppUrl } from '../_utils';
import type { SupportFormData } from '../_utils';

const DESC_MAX = 1000;
const DESC_MIN = 10;

interface FieldErrors {
    businessName?: string;
    email?: string;
    product?: string;
    description?: string;
}

function validate(data: SupportFormData): FieldErrors {
    const errors: FieldErrors = {};

    if (!data.businessName.trim()) {
        errors.businessName = 'Ingresá el nombre del comercio o local';
    }

    if (!data.email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email.trim())) {
        errors.email = 'Ingresá un email válido';
    }

    if (!data.product) {
        errors.product = 'Seleccioná el producto o módulo consultado';
    }

    const desc = data.description.trim();
    if (!desc || desc.length < DESC_MIN) {
        errors.description = 'Describí brevemente el problema para poder ayudarte';
    }

    return errors;
}

function hasErrors(errors: FieldErrors): boolean {
    return Object.keys(errors).length > 0;
}

export function SupportForm() {
    const formId = useId();
    const [data, setData] = useState<SupportFormData>({
        businessName: '',
        email: '',
        product: '',
        description: '',
        extra: '',
    });
    const [errors, setErrors] = useState<FieldErrors>({});
    const [touched, setTouched] = useState<Record<string, boolean>>({});

    function handleChange(
        e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
    ) {
        const { name, value } = e.target;
        setData((prev) => ({ ...prev, [name]: value }));
        if (touched[name]) {
            setErrors((prev) => {
                const next = validate({ ...data, [name]: value });
                return { ...prev, [name]: next[name as keyof FieldErrors] ?? undefined };
            });
        }
    }

    function handleBlur(e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) {
        const { name } = e.target;
        setTouched((prev) => ({ ...prev, [name]: true }));
        const next = validate(data);
        setErrors((prev) => ({ ...prev, [name]: next[name as keyof FieldErrors] ?? undefined }));
    }

    function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        const allErrors = validate(data);
        setErrors(allErrors);
        setTouched({ businessName: true, email: true, product: true, description: true });

        if (hasErrors(allErrors)) return;

        const message = buildSupportMessage(data);
        const url = buildWhatsAppUrl(message);
        window.open(url, '_blank', 'noopener,noreferrer');
    }

    const currentErrors = validate(data);
    const isDisabled = hasErrors(currentErrors);

    const fieldBase =
        'w-full rounded-lg border bg-white px-4 py-2.5 text-sm text-slate-900 shadow-sm transition-colors placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-1';
    const fieldValid = 'border-slate-300 hover:border-slate-400';
    const fieldError = 'border-red-400 focus:ring-red-500';

    function fieldCls(name: keyof FieldErrors) {
        return `${fieldBase} ${errors[name] && touched[name] ? fieldError : fieldValid}`;
    }

    function errorId(name: string) {
        return `${formId}-${name}-error`;
    }

    return (
        <form
            onSubmit={handleSubmit}
            noValidate
            className="space-y-5"
        >
            {/* Nombre del comercio */}
            <div>
                <label htmlFor={`${formId}-businessName`} className="mb-1.5 block text-sm font-medium text-slate-700">
                    Nombre del comercio o local
                </label>
                <input
                    id={`${formId}-businessName`}
                    name="businessName"
                    type="text"
                    required
                    value={data.businessName}
                    onChange={handleChange}
                    onBlur={handleBlur}
                    className={fieldCls('businessName')}
                    aria-describedby={errors.businessName && touched.businessName ? errorId('businessName') : undefined}
                    aria-invalid={!!(errors.businessName && touched.businessName)}
                />
                {errors.businessName && touched.businessName && (
                    <p id={errorId('businessName')} className="mt-1.5 text-xs text-red-600" role="alert">
                        {errors.businessName}
                    </p>
                )}
            </div>

            {/* Email */}
            <div>
                <label htmlFor={`${formId}-email`} className="mb-1.5 block text-sm font-medium text-slate-700">
                    Email con el que te registraste
                </label>
                <input
                    id={`${formId}-email`}
                    name="email"
                    type="email"
                    required
                    value={data.email}
                    onChange={handleChange}
                    onBlur={handleBlur}
                    className={fieldCls('email')}
                    aria-describedby={errors.email && touched.email ? errorId('email') : undefined}
                    aria-invalid={!!(errors.email && touched.email)}
                />
                {errors.email && touched.email && (
                    <p id={errorId('email')} className="mt-1.5 text-xs text-red-600" role="alert">
                        {errors.email}
                    </p>
                )}
            </div>

            {/* Producto / módulo */}
            <div>
                <label htmlFor={`${formId}-product`} className="mb-1.5 block text-sm font-medium text-slate-700">
                    Producto o módulo consultado
                </label>
                <select
                    id={`${formId}-product`}
                    name="product"
                    required
                    value={data.product}
                    onChange={handleChange}
                    onBlur={handleBlur}
                    className={fieldCls('product')}
                    aria-describedby={errors.product && touched.product ? errorId('product') : undefined}
                    aria-invalid={!!(errors.product && touched.product)}
                >
                    {PRODUCT_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value} disabled={opt.value === ''}>
                            {opt.label}
                        </option>
                    ))}
                </select>
                {errors.product && touched.product && (
                    <p id={errorId('product')} className="mt-1.5 text-xs text-red-600" role="alert">
                        {errors.product}
                    </p>
                )}
            </div>

            {/* Descripción */}
            <div>
                <label htmlFor={`${formId}-description`} className="mb-1.5 block text-sm font-medium text-slate-700">
                    Breve descripción del problema
                </label>
                <textarea
                    id={`${formId}-description`}
                    name="description"
                    required
                    rows={4}
                    maxLength={DESC_MAX}
                    value={data.description}
                    onChange={handleChange}
                    onBlur={handleBlur}
                    className={`${fieldCls('description')} resize-none`}
                    aria-describedby={
                        [
                            errors.description && touched.description ? errorId('description') : null,
                            `${formId}-description-count`,
                        ]
                            .filter(Boolean)
                            .join(' ') || undefined
                    }
                    aria-invalid={!!(errors.description && touched.description)}
                />
                <div className="mt-1.5 flex items-start justify-between gap-4">
                    {errors.description && touched.description ? (
                        <p id={errorId('description')} className="text-xs text-red-600" role="alert">
                            {errors.description}
                        </p>
                    ) : (
                        <span />
                    )}
                    <p id={`${formId}-description-count`} className="shrink-0 text-xs text-slate-400">
                        {data.description.length}/{DESC_MAX}
                    </p>
                </div>
            </div>

            {/* Capturas / extra (opcional) */}
            <div>
                <label htmlFor={`${formId}-extra`} className="mb-1.5 block text-sm font-medium text-slate-700">
                    Capturas de pantalla o información adicional{' '}
                    <span className="font-normal text-slate-400">(opcional)</span>
                </label>
                <textarea
                    id={`${formId}-extra`}
                    name="extra"
                    rows={3}
                    value={data.extra}
                    onChange={handleChange}
                    placeholder="Podés describir acá si tenés capturas, errores visibles o detalles extra"
                    className={`${fieldBase} ${fieldValid} resize-none`}
                />
            </div>

            {/* Submit */}
            <button
                type="submit"
                disabled={isDisabled}
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-green-600 px-6 py-3 text-sm font-semibold text-white shadow-sm transition-all hover:bg-green-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
                <MessageSquare className="h-4 w-4" />
                Enviar consulta por WhatsApp
            </button>
        </form>
    );
}
