"use client";

import { useState } from 'react';

import { Modal } from '@/components/ui/modal';
import { useCustomerContactPreferences, useUpdateCustomerContactPreferences } from '@/features/customers/hooks';
import type {
    ContactChannel,
    ContactConsentSource,
    CustomerContactPreferences as Preferences,
    CustomerContactPreferencesPayload,
} from '@/features/customers/types';
import { ApiError } from '@/lib/api/client';
import { calendarParts, dateInTimeZone } from '@/lib/business-time';

import { MONTHS } from './customer-upcoming-appointments';

export const CHANNEL_LABELS: Record<ContactChannel, string> = {
    whatsapp: 'WhatsApp',
    email: 'Email',
    phone: 'Llamadas',
};

const PREFERRED_LABELS: Record<ContactChannel, string> = {
    whatsapp: 'WhatsApp',
    email: 'Email',
    phone: 'Llamada',
};

const CHANNELS: ContactChannel[] = ['whatsapp', 'email', 'phone'];
/** Encenderlos exige confirmar consentimiento (mismo set que el backend). */
const CONSENT_CHANNELS = ['whatsapp', 'email'] as const;
type ConsentChannel = (typeof CONSENT_CHANNELS)[number];

const SOURCE_LABELS: Record<ContactConsentSource, string> = {
    manual: 'registrado por el equipo',
    customer_request: 'pedido del cliente',
    public_booking: 'reserva online',
    imported: 'importado',
};

export const DO_NOT_CONTACT_COPY = 'El cliente pidió no ser contactado: ningún canal automático se va a usar.';

/** "02 oct 2026" en la zona del Business. */
function formatConsentDay(iso: string, timeZone: string) {
    const { year, monthIndex, day } = calendarParts(dateInTimeZone(iso, timeZone));
    return `${String(day).padStart(2, '0')} ${MONTHS[monthIndex]} ${year}`;
}

function resolveApiError(error: unknown, fallback: string) {
    if (error instanceof ApiError && error.payload && typeof error.payload === 'object') {
        const payload = error.payload as Record<string, unknown>;
        if (typeof payload.detail === 'string') return payload.detail;
        if (typeof payload.message === 'string') return payload.message;
        const first = Object.values(payload).find((value) => Array.isArray(value) && value.length > 0);
        if (Array.isArray(first) && typeof first[0] === 'string') return first[0];
    }
    return fallback;
}

function hasDestinationData(channel: ContactChannel, phone: string | null, email: string | null) {
    return Boolean(channel === 'email' ? email?.trim() : phone?.trim());
}

/** Aviso cuando falta el dato de contacto del canal (no se inventa nada). */
function missingDataWarning(channel: ContactChannel, phone: string | null, email: string | null): string | null {
    if (hasDestinationData(channel, phone, email)) return null;
    return channel === 'email'
        ? 'Este cliente no tiene email cargado: cargalo en la ficha antes de autorizar este canal.'
        : channel === 'phone'
          ? 'Este cliente no tiene teléfono cargado.'
          : 'Este cliente no tiene teléfono cargado: cargalo en la ficha antes de autorizar este canal.';
}

/** CUSTOMER 07D.1.1: razones que se resuelven renovando la autorización (las decide el backend). */
const RENEWABLE_REASONS = new Set(['consent_missing', 'consent_destination_changed']);

export function needsConsentRenewal(prefs: Preferences, channel: ContactChannel) {
    return RENEWABLE_REASONS.has(prefs.channels[channel].reason ?? '');
}

function channelReasonWarning(prefs: Preferences, channel: ContactChannel): string | null {
    switch (prefs.channels[channel].reason) {
        case 'missing_phone':
            return 'Falta el teléfono: no se puede usar.';
        case 'invalid_phone':
            return 'El teléfono no es válido para WhatsApp.';
        case 'missing_email':
            return 'Falta el email: no se puede usar.';
        case 'consent_destination_changed':
            return channel === 'email'
                ? 'El email cambió desde la última autorización. Volvé a confirmar el consentimiento para usar Email automáticamente.'
                : 'El teléfono cambió desde la última autorización. Volvé a confirmar el consentimiento para usar WhatsApp automáticamente.';
        case 'consent_missing':
            return 'No hay un destino autorizado registrado. Volvé a confirmar el consentimiento para usar este canal automáticamente.';
        default:
            return null;
    }
}

/**
 * Preferencias de contacto del cliente (CUSTOMER 07D.1), sección propia de la
 * ficha. Solo mensajes OPERATIVOS (turnos, recordatorios); no marketing. Nada
 * se envía todavía. Lectura con `view_customers`; editar solo con
 * `manage_customer_contact_preferences` (`canManage`: owner/admin/manager) y
 * el backend lo vuelve a exigir.
 */
export function CustomerContactPreferences({
    customerId,
    phone,
    email,
    canManage,
    timeZone,
}: {
    customerId: string;
    phone: string | null;
    email: string | null;
    canManage: boolean;
    timeZone: string;
}) {
    const [editing, setEditing] = useState(false);
    const query = useCustomerContactPreferences(customerId);
    const prefs = query.data;

    return (
        <section aria-label="Preferencias de contacto" className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                    <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Preferencias de contacto</h3>
                    <p className="text-xs text-slate-400">Estas preferencias se usarán para futuros recordatorios y comunicaciones automáticas.</p>
                </div>
                {canManage && prefs ? (
                    <button
                        type="button"
                        onClick={() => setEditing(true)}
                        className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900"
                    >
                        Editar preferencias
                    </button>
                ) : null}
            </div>

            {query.isLoading ? (
                <p className="mt-3 text-sm text-slate-500">Cargando preferencias...</p>
            ) : query.isError || !prefs ? (
                <p role="alert" className="mt-3 text-sm text-rose-600">
                    {resolveApiError(query.error, 'No pudimos cargar las preferencias de contacto.')}
                </p>
            ) : (
                <>
                    {prefs.do_not_contact ? (
                        <p role="status" data-testid="do-not-contact-banner" className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-700">
                            No contactar. {DO_NOT_CONTACT_COPY} Las preferencias de abajo se conservan.
                        </p>
                    ) : null}
                    <ul className="mt-3 divide-y divide-slate-100">
                        {CHANNELS.map((channel) => {
                            const enabled = prefs[`${channel}_enabled`];
                            const consentAt = channel === 'phone' ? null : prefs[`${channel}_consent_at`];
                            const consentSource = channel === 'phone' ? null : prefs[`${channel}_consent_source`];
                            const warning = enabled && !prefs.do_not_contact ? channelReasonWarning(prefs, channel) : null;
                            return (
                                <li key={channel} data-testid={`contact-channel-${channel}`} className="flex flex-col gap-0.5 py-2 sm:flex-row sm:items-baseline sm:justify-between sm:gap-3">
                                    <div className="min-w-0">
                                        <p className="text-sm font-semibold text-slate-800">
                                            {CHANNEL_LABELS[channel]}
                                            {prefs.preferred_channel === channel ? (
                                                <span className="ml-2 rounded-full bg-slate-900 px-2 py-0.5 text-[11px] font-semibold text-white">Preferido</span>
                                            ) : null}
                                        </p>
                                        {channel === 'phone' ? <p className="text-xs text-slate-400">Solo manual: nunca automático.</p> : null}
                                        {consentAt ? (
                                            <p className="text-xs text-slate-500">
                                                {enabled ? 'Autorizado' : 'Autorización registrada'} el {formatConsentDay(consentAt, timeZone)}
                                                {consentSource ? ` · ${SOURCE_LABELS[consentSource]}` : ''}
                                                {enabled ? '' : ' (canal apagado)'}
                                            </p>
                                        ) : null}
                                        {channel !== 'phone' && prefs.channels[channel].usable ? (
                                            <p className="text-xs text-emerald-700">Listo para avisos automáticos.</p>
                                        ) : null}
                                        {warning ? <p className="text-xs font-semibold text-amber-700">{warning}</p> : null}
                                        {canManage && enabled && needsConsentRenewal(prefs, channel) ? (
                                            <button
                                                type="button"
                                                onClick={() => setEditing(true)}
                                                className="mt-1 min-h-11 w-fit rounded-full border border-amber-300 px-3 text-xs font-semibold text-amber-800 hover:border-amber-500 sm:min-h-0 sm:py-1"
                                            >
                                                Renovar autorización
                                            </button>
                                        ) : null}
                                    </div>
                                    <span
                                        className={`w-fit shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}
                                    >
                                        {enabled ? 'Permitido' : 'No permitido'}
                                    </span>
                                </li>
                            );
                        })}
                    </ul>
                    {!prefs.preferred_channel ? <p className="mt-1 text-xs text-slate-500">Sin canal preferido.</p> : null}
                </>
            )}

            {canManage && editing && prefs ? (
                <ContactPreferencesFormModal
                    customerId={customerId}
                    prefs={prefs}
                    phone={phone}
                    email={email}
                    onClose={() => setEditing(false)}
                />
            ) : null}
        </section>
    );
}

function ContactPreferencesFormModal({
    customerId,
    prefs,
    phone,
    email,
    onClose,
}: {
    customerId: string;
    prefs: Preferences;
    phone: string | null;
    email: string | null;
    onClose: () => void;
}) {
    const [enabled, setEnabled] = useState<Record<ContactChannel, boolean>>({
        whatsapp: prefs.whatsapp_enabled,
        email: prefs.email_enabled,
        phone: prefs.phone_enabled,
    });
    const [preferred, setPreferred] = useState<ContactChannel | null>(prefs.preferred_channel);
    const [doNotContact, setDoNotContact] = useState(prefs.do_not_contact);
    const [consent, setConsent] = useState<Record<ConsentChannel, boolean>>({ whatsapp: false, email: false });
    const [consentSource, setConsentSource] = useState<'manual' | 'customer_request'>('manual');
    const [error, setError] = useState<string | null>(null);
    const mutation = useUpdateCustomerContactPreferences(customerId);

    // Encender (apagado → encendido) exige confirmar. CUSTOMER 07D.1.1: si el
    // backend dice que el destino autorizado ya no corresponde, se ofrece
    // renovar (opcional: sin renovar se pueden guardar otros cambios).
    const enabling = CONSENT_CHANNELS.filter((channel) => enabled[channel] && !prefs[`${channel}_enabled`]);
    const renewable = CONSENT_CHANNELS.filter(
        (channel) => enabled[channel] && prefs[`${channel}_enabled`] && needsConsentRenewal(prefs, channel),
    );
    const missingConsent = enabling.filter((channel) => !consent[channel]);
    const confirming = [...enabling, ...renewable].filter((channel) => consent[channel]);

    const toggleChannel = (channel: ContactChannel, value: boolean) => {
        setEnabled((current) => ({ ...current, [channel]: value }));
        // Un canal apagado no puede quedar como preferido (el backend lo rechaza).
        if (!value && preferred === channel) setPreferred(null);
        if (!value && channel !== 'phone') setConsent((current) => ({ ...current, [channel]: false }));
    };

    const handleSave = async () => {
        if (missingConsent.length > 0) {
            setError('Confirmá que el cliente autorizó los canales que activaste.');
            return;
        }
        setError(null);
        const payload: CustomerContactPreferencesPayload = {
            whatsapp_enabled: enabled.whatsapp,
            email_enabled: enabled.email,
            phone_enabled: enabled.phone,
            preferred_channel: preferred,
            do_not_contact: doNotContact,
        };
        for (const channel of confirming) payload[`${channel}_consent_confirmed`] = true;
        if (confirming.length > 0) payload.consent_source = consentSource;
        try {
            await mutation.mutateAsync(payload);
            onClose();
        } catch (err) {
            setError(resolveApiError(err, 'No pudimos guardar las preferencias. Intentá nuevamente.'));
        }
    };

    const footer = (
        <div className="space-y-3">
            {error ? (
                <p role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                    {error}
                </p>
            ) : null}
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end sm:gap-3">
                <button
                    type="button"
                    onClick={onClose}
                    className="rounded-full border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900 sm:py-2"
                >
                    Cancelar
                </button>
                <button
                    type="button"
                    disabled={mutation.isPending || missingConsent.length > 0}
                    onClick={handleSave}
                    className="rounded-full border border-slate-900 bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-200 sm:py-2"
                >
                    {mutation.isPending ? 'Guardando...' : 'Guardar preferencias'}
                </button>
            </div>
        </div>
    );

    return (
        <Modal open eyebrow={null} title="Preferencias de contacto" onClose={onClose} footer={footer}>
            <p className="text-sm text-slate-500">
                Estas preferencias se usarán para futuros recordatorios y comunicaciones automáticas. Solo mensajes sobre sus turnos, no
                promociones.
            </p>

            <fieldset className="space-y-3">
                <legend className="sr-only">Canales permitidos</legend>
                {CHANNELS.map((channel) => {
                    const inputId = `contact-pref-${channel}`;
                    const warning = enabled[channel] || channel !== 'phone' ? missingDataWarning(channel, phone, email) : null;
                    const enablingChannel = channel !== 'phone' && enabling.includes(channel as ConsentChannel);
                    const renewing = channel !== 'phone' && renewable.includes(channel as ConsentChannel);
                    // Sin dato de contacto no hay destino que autorizar (el backend lo rechaza igual).
                    const cannotAuthorize = channel !== 'phone' && !prefs[`${channel}_enabled`] && !hasDestinationData(channel, phone, email);
                    const destination = channel === 'email' ? email?.trim() : phone?.trim();
                    return (
                        <div key={channel} className="rounded-2xl border border-slate-200 px-4 py-3">
                            <p className="text-sm font-semibold text-slate-800">{CHANNEL_LABELS[channel]}</p>
                            <label htmlFor={inputId} className="mt-1 flex min-h-11 items-center gap-3 text-sm text-slate-700 sm:min-h-0">
                                <input
                                    id={inputId}
                                    type="checkbox"
                                    checked={enabled[channel]}
                                    disabled={cannotAuthorize}
                                    onChange={(event) => toggleChannel(channel, event.target.checked)}
                                    className="h-5 w-5 shrink-0 rounded border-slate-300"
                                />
                                Permitido
                            </label>
                            {channel === 'phone' ? <p className="text-xs text-slate-400">Las llamadas son siempre manuales.</p> : null}
                            {enablingChannel || renewing ? (
                                <label
                                    htmlFor={`${inputId}-consent`}
                                    className="mt-2 flex items-start gap-3 rounded-xl bg-amber-50 px-3 py-2 text-sm font-medium text-amber-900"
                                >
                                    <input
                                        id={`${inputId}-consent`}
                                        type="checkbox"
                                        // Nombre explícito: con el texto en bloques anidados el árbol de accesibilidad lo exponía como "on".
                                        aria-label={`Confirmo que el cliente autorizó este canal (${CHANNEL_LABELS[channel]})`}
                                        checked={consent[channel as ConsentChannel]}
                                        onChange={(event) => setConsent((current) => ({ ...current, [channel]: event.target.checked }))}
                                        className="mt-0.5 h-5 w-5 shrink-0 rounded border-amber-400"
                                    />
                                    <span>
                                        {renewing ? (
                                            <span className="block text-xs font-semibold">{channelReasonWarning(prefs, channel)}</span>
                                        ) : null}
                                        Confirmo que el cliente autorizó este canal.
                                        {destination ? <span className="block text-xs font-normal text-amber-800">Destino: {destination}</span> : null}
                                    </span>
                                </label>
                            ) : null}
                            {warning ? (
                                <p role="note" className="mt-2 text-xs font-semibold text-amber-700">
                                    {warning}
                                </p>
                            ) : null}
                        </div>
                    );
                })}
            </fieldset>

            {enabling.length > 0 || confirming.length > 0 ? (
                <div>
                    <label htmlFor="contact-pref-source" className="block text-sm font-medium text-slate-700">
                        ¿Cómo se obtuvo la autorización?
                    </label>
                    <select
                        id="contact-pref-source"
                        value={consentSource}
                        onChange={(event) => setConsentSource(event.target.value as 'manual' | 'customer_request')}
                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2.5 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
                    >
                        <option value="manual">Lo registró el equipo</option>
                        <option value="customer_request">El cliente lo pidió</option>
                    </select>
                </div>
            ) : null}

            <div>
                <label htmlFor="contact-pref-preferred" className="block text-sm font-medium text-slate-700">
                    Canal preferido
                </label>
                <select
                    id="contact-pref-preferred"
                    value={preferred ?? ''}
                    onChange={(event) => setPreferred((event.target.value || null) as ContactChannel | null)}
                    className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2.5 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
                >
                    <option value="">Sin preferencia</option>
                    {CHANNELS.map((channel) => (
                        <option key={channel} value={channel} disabled={!enabled[channel]}>
                            {PREFERRED_LABELS[channel]}
                            {enabled[channel] ? '' : ' (no permitido)'}
                        </option>
                    ))}
                </select>
            </div>

            <div className="rounded-2xl border border-rose-200 px-4 py-3">
                <label htmlFor="contact-pref-dnc" className="flex min-h-11 items-center gap-3 text-sm font-semibold text-rose-700 sm:min-h-0">
                    <input
                        id="contact-pref-dnc"
                        type="checkbox"
                        checked={doNotContact}
                        onChange={(event) => setDoNotContact(event.target.checked)}
                        className="h-5 w-5 shrink-0 rounded border-rose-300"
                    />
                    No contactar
                </label>
                <p className="text-xs text-slate-500">
                    {doNotContact
                        ? `${DO_NOT_CONTACT_COPY} Los canales de arriba se conservan pero quedan en pausa.`
                        : 'Si el cliente pide no ser contactado, marcalo: tiene prioridad sobre cualquier canal.'}
                </p>
            </div>
        </Modal>
    );
}
