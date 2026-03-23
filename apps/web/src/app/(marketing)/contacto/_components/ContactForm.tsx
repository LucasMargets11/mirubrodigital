'use client';

import { useState, useId } from 'react';
import { MessageSquare, Mail } from 'lucide-react';
import { INQUIRY_OPTIONS, PREFERRED_CHANNEL_OPTIONS } from '../_constants';
import {
    buildContactWhatsAppMessage,
    buildContactMailtoLink,
    getContactWhatsAppUrl,
} from '../_utils';
import type { ContactFormData } from '../_utils';

const MSG_MAX = 1000;
const MSG_MIN = 10;

interface FieldErrors {
    fullName?: string;
    email?: string;
    inquiryType?: string;
    message?: string;
    phone?: string;
}

function validate(data: ContactFormData): FieldErrors {
    const errors: FieldErrors = {};

    if (!data.fullName.trim()) {
        errors.fullName = 'Ingresá tu nombre y apellido';
    }

    if (
        !data.email.trim() ||
        !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email.trim())
    ) {
        errors.email = 'Ingresá un email válido';
    }

    if (!data.inquiryType) {
        errors.inquiryType = 'Seleccioná el tipo de consulta';
    }

    const msg = data.message.trim();
    if (!msg || msg.length < MSG_MIN) {
        errors.message = 'Contanos brevemente qué necesitás';
    }

    if (data.preferredChannel === 'WhatsApp' && !data.phone.trim()) {
        errors.phone =
            'Si preferís que te respondamos por WhatsApp, ingresá un número de contacto';
    }

    return errors;
}

function hasErrors(errors: FieldErrors): boolean {
    return Object.keys(errors).length > 0;
}

export function ContactForm() {
    const formId = useId();
    const [data, setData] = useState<ContactFormData>({
        fullName: '',
        businessName: '',
        email: '',
        inquiryType: '',
        message: '',
        preferredChannel: 'Email',
        phone: '',
    });
    const [errors, setErrors] = useState<FieldErrors>({});
    const [touched, setTouched] = useState<Record<string, boolean>>({});

    function handleChange(
        e: React.ChangeEvent<
            HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
        >,
    ) {
        const { name, value } = e.target;
        setData((prev) => ({ ...prev, [name]: value }));
        if (touched[name]) {
            setErrors((prev) => {
                const next = validate({ ...data, [name]: value });
                return {
                    ...prev,
                    [name]: next[name as keyof FieldErrors] ?? undefined,
                };
            });
        }
    }

    function handleBlur(
        e: React.FocusEvent<
            HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
        >,
    ) {
        const { name } = e.target;
        setTouched((prev) => ({ ...prev, [name]: true }));
        const next = validate(data);
        setErrors((prev) => ({
            ...prev,
            [name]: next[name as keyof FieldErrors] ?? undefined,
        }));
    }

    function runValidation(): boolean {
        const allErrors = validate(data);
        setErrors(allErrors);
        setTouched({
            fullName: true,
            email: true,
            inquiryType: true,
            message: true,
            phone: true,
        });
        return !hasErrors(allErrors);
    }

    function handleWhatsApp(e: React.FormEvent) {
        e.preventDefault();
        if (!runValidation()) return;
        const msg = buildContactWhatsAppMessage(data);
        const url = getContactWhatsAppUrl(msg);
        window.open(url, '_blank', 'noopener,noreferrer');
    }

    function handleEmail(e: React.MouseEvent) {
        e.preventDefault();
        if (!runValidation()) return;
        const mailto = buildContactMailtoLink(data);
        window.location.href = mailto;
    }

    /* ── Styling helpers ── */
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
        <form onSubmit={handleWhatsApp} noValidate className="space-y-5">
            {/* Nombre y apellido */}
            <div>
                <label
                    htmlFor={`${formId}-fullName`}
                    className="mb-1.5 block text-sm font-medium text-slate-700"
                >
                    Nombre y apellido<span className="text-red-500"> *</span>
                </label>
                <input
                    id={`${formId}-fullName`}
                    name="fullName"
                    type="text"
                    required
                    value={data.fullName}
                    onChange={handleChange}
                    onBlur={handleBlur}
                    className={fieldCls('fullName')}
                    aria-describedby={
                        errors.fullName && touched.fullName
                            ? errorId('fullName')
                            : undefined
                    }
                    aria-invalid={!!(errors.fullName && touched.fullName)}
                />
                {errors.fullName && touched.fullName && (
                    <p
                        id={errorId('fullName')}
                        className="mt-1.5 text-xs text-red-600"
                        role="alert"
                    >
                        {errors.fullName}
                    </p>
                )}
            </div>

            {/* Comercio o local */}
            <div>
                <label
                    htmlFor={`${formId}-businessName`}
                    className="mb-1.5 block text-sm font-medium text-slate-700"
                >
                    Nombre del comercio o local
                    <span className="ml-1 text-xs font-normal text-slate-400">
                        (opcional)
                    </span>
                </label>
                <input
                    id={`${formId}-businessName`}
                    name="businessName"
                    type="text"
                    value={data.businessName}
                    onChange={handleChange}
                    className={`${fieldBase} ${fieldValid}`}
                />
            </div>

            {/* Email */}
            <div>
                <label
                    htmlFor={`${formId}-email`}
                    className="mb-1.5 block text-sm font-medium text-slate-700"
                >
                    Email<span className="text-red-500"> *</span>
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
                    aria-describedby={
                        errors.email && touched.email
                            ? errorId('email')
                            : undefined
                    }
                    aria-invalid={!!(errors.email && touched.email)}
                />
                {errors.email && touched.email && (
                    <p
                        id={errorId('email')}
                        className="mt-1.5 text-xs text-red-600"
                        role="alert"
                    >
                        {errors.email}
                    </p>
                )}
            </div>

            {/* Tipo de consulta */}
            <div>
                <label
                    htmlFor={`${formId}-inquiryType`}
                    className="mb-1.5 block text-sm font-medium text-slate-700"
                >
                    Tipo de consulta<span className="text-red-500"> *</span>
                </label>
                <select
                    id={`${formId}-inquiryType`}
                    name="inquiryType"
                    required
                    value={data.inquiryType}
                    onChange={handleChange}
                    onBlur={handleBlur}
                    className={fieldCls('inquiryType')}
                    aria-describedby={
                        errors.inquiryType && touched.inquiryType
                            ? errorId('inquiryType')
                            : undefined
                    }
                    aria-invalid={
                        !!(errors.inquiryType && touched.inquiryType)
                    }
                >
                    {INQUIRY_OPTIONS.map((opt) => (
                        <option
                            key={opt.value}
                            value={opt.value}
                            disabled={opt.value === ''}
                        >
                            {opt.label}
                        </option>
                    ))}
                </select>
                {errors.inquiryType && touched.inquiryType && (
                    <p
                        id={errorId('inquiryType')}
                        className="mt-1.5 text-xs text-red-600"
                        role="alert"
                    >
                        {errors.inquiryType}
                    </p>
                )}
            </div>

            {/* Mensaje */}
            <div>
                <label
                    htmlFor={`${formId}-message`}
                    className="mb-1.5 block text-sm font-medium text-slate-700"
                >
                    Mensaje<span className="text-red-500"> *</span>
                </label>
                <textarea
                    id={`${formId}-message`}
                    name="message"
                    required
                    rows={4}
                    maxLength={MSG_MAX}
                    value={data.message}
                    onChange={handleChange}
                    onBlur={handleBlur}
                    className={`${fieldCls('message')} resize-none`}
                    aria-describedby={
                        errors.message && touched.message
                            ? errorId('message')
                            : undefined
                    }
                    aria-invalid={!!(errors.message && touched.message)}
                />
                <div className="mt-1 flex items-center justify-between">
                    {errors.message && touched.message ? (
                        <p
                            id={errorId('message')}
                            className="text-xs text-red-600"
                            role="alert"
                        >
                            {errors.message}
                        </p>
                    ) : (
                        <span />
                    )}
                    <span className="text-xs text-slate-400">
                        {data.message.length}/{MSG_MAX}
                    </span>
                </div>
            </div>

            {/* Canal preferido */}
            <fieldset>
                <legend className="mb-2 block text-sm font-medium text-slate-700">
                    Canal preferido de respuesta
                    <span className="text-red-500"> *</span>
                </legend>
                <div className="flex gap-6">
                    {PREFERRED_CHANNEL_OPTIONS.map((opt) => (
                        <label
                            key={opt.value}
                            className="flex items-center gap-2 text-sm text-slate-700"
                        >
                            <input
                                type="radio"
                                name="preferredChannel"
                                value={opt.value}
                                checked={data.preferredChannel === opt.value}
                                onChange={handleChange}
                                className="h-4 w-4 border-slate-300 text-brand-600 focus:ring-brand-500"
                            />
                            {opt.label}
                        </label>
                    ))}
                </div>
            </fieldset>

            {/* Teléfono */}
            <div>
                <label
                    htmlFor={`${formId}-phone`}
                    className="mb-1.5 block text-sm font-medium text-slate-700"
                >
                    Teléfono / WhatsApp de contacto
                    <span className="ml-1 text-xs font-normal text-slate-400">
                        (opcional)
                    </span>
                </label>
                <input
                    id={`${formId}-phone`}
                    name="phone"
                    type="tel"
                    value={data.phone}
                    onChange={handleChange}
                    onBlur={handleBlur}
                    className={fieldCls('phone')}
                    aria-describedby={
                        errors.phone && touched.phone
                            ? errorId('phone')
                            : undefined
                    }
                    aria-invalid={!!(errors.phone && touched.phone)}
                />
                {errors.phone && touched.phone && (
                    <p
                        id={errorId('phone')}
                        className="mt-1.5 text-xs text-red-600"
                        role="alert"
                    >
                        {errors.phone}
                    </p>
                )}
            </div>

            {/* Botones */}
            <div className="flex flex-col gap-3 pt-2 sm:flex-row">
                <button
                    type="submit"
                    className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-green-600 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-green-500 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-1"
                >
                    <MessageSquare className="h-4 w-4" />
                    Enviar por WhatsApp
                </button>

                <button
                    type="button"
                    onClick={handleEmail}
                    className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-brand-300 hover:text-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-1"
                >
                    <Mail className="h-4 w-4" />
                    Escribir por email
                </button>
            </div>
        </form>
    );
}
