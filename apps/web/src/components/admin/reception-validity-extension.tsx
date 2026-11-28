'use client';

import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';

import { Button } from '@/components/ui/button';
import { DatePicker } from '@/components/ui/date-picker';
import { Modal } from '@/components/ui/modal';
import { aiUsageTierLabel } from '@/features/reception/ai-usage-summary-panel';
import { extendAdminReceptionSubscription } from '@/features/reception/api';
import { adminAIUsageKey } from '@/features/reception/hooks';
import { errorCode } from '@/features/reception/receptionist-config-form';
import type { AdminAIUsageOverview } from '@/features/reception/types';
import { addCalendarMonths } from '@/lib/admin/complimentary-period';
import { ApiError } from '@/lib/api/client';
import { addDaysToDateString, dateStringFromTimestampAR, formatDateFromTimestampAR, todayDateString } from '@/lib/dates';

type SourceSubscription = NonNullable<AdminAIUsageOverview['source_subscription']>;

export const EXTENSION_REASON_MAX = 255;

/**
 * Bonificación manual de Recepcionista potencialmente extendible, a partir de
 * la fuente comercial real del consumo (`source_subscription`, nunca la
 * suscripción principal del comercio). Es solo una guía para mostrar la
 * acción: el backend (PROD-09D1) conserva la autoridad final.
 */
export function extendableReceptionSubscription(
    overview: AdminAIUsageOverview | null | undefined,
    now: number = Date.now(),
): SourceSubscription | null {
    const sub = overview?.source_subscription;
    if (!sub) return null;
    const end = sub.current_period_end ? Date.parse(sub.current_period_end) : Number.NaN;
    const start = sub.current_period_start ? Date.parse(sub.current_period_start) : Number.NaN;
    const ok = sub.service_type === 'reception'
        && sub.plan_code === 'reception'
        && sub.provider === 'manual'
        && sub.complimentary
        && sub.status === 'trialing'
        && !sub.cancel_at_period_end
        && Number.isFinite(start) && start <= now
        && Number.isFinite(end) && end > now;
    return ok ? sub : null;
}

type FieldErrors = { complimentary_end?: string; reason?: string };
type Failure = { text: string; reload?: boolean; fields?: FieldErrors };

/** Datos comerciales que cambiaron desde la lectura: se ofrece recargar, nunca reintentar. */
const STALE: Record<string, string> = {
    subscription_not_found: 'La suscripción ya no pertenece a este cliente.',
    subscription_canceled: 'La suscripción fue cancelada.',
    subscription_suspended: 'La suscripción está suspendida; la extensión no la reactiva.',
    subscription_not_current: 'La bonificación ya no está vigente (vencida o sin comenzar).',
    subscription_not_complimentary: 'La suscripción ya no es una bonificación manual.',
    subscription_not_extendable: 'La suscripción no es una bonificación de Recepcionista IA.',
    cancellation_scheduled: 'La suscripción tiene una baja programada.',
    custom_policy_not_extendable: 'La política de consumo personalizada no se puede extender (revocada, ausente o no alineada con el vencimiento).',
    client_not_found: 'El cliente ya no existe como negocio principal.',
};

function firstMessage(value: unknown): string | undefined {
    if (Array.isArray(value) && typeof value[0] === 'string') return value[0];
    return typeof value === 'string' ? value : undefined;
}

export function extensionFailure(error: unknown): Failure {
    const code = errorCode(error);
    if (code === 'invalid_end') {
        return {
            text: 'Revisá la nueva fecha de vencimiento.',
            fields: { complimentary_end: 'Tiene que ser posterior al vencimiento actual.' },
        };
    }
    if (code === 'invalid_reason') {
        return { text: 'Revisá el motivo.', fields: { reason: `Indicá un motivo de 1 a ${EXTENSION_REASON_MAX} caracteres.` } };
    }
    if (code && STALE[code]) {
        return { text: `${STALE[code]} No se cambió nada. Recargá los datos comerciales.`, reload: true };
    }
    if (error instanceof ApiError && error.status === 403) {
        return { text: 'Solo un superadmin puede extender la vigencia. No se cambió nada.' };
    }
    if (error instanceof ApiError && error.status === 400 && !code) {
        // Errores de forma del serializer: `{campo: [mensajes]}`.
        const payload = (error.payload ?? {}) as Record<string, unknown>;
        const fields: FieldErrors = {
            complimentary_end: firstMessage(payload.complimentary_end),
            reason: firstMessage(payload.reason),
        };
        if (fields.complimentary_end || fields.reason) return { text: 'Revisá los datos ingresados.', fields };
    }
    if (error instanceof ApiError && error.status === 404) {
        return { text: 'No encontramos la suscripción. No se cambió nada. Recargá los datos comerciales.', reload: true };
    }
    return { text: 'No pudimos extender la vigencia. No se cambió nada; podés intentarlo nuevamente.' };
}

type Props = {
    businessId: number;
    businessName: string;
    subscription: SourceSubscription;
};

/**
 * PROD-09D2 — «Extender vigencia» de la bonificación de Recepcionista IA
 * (superadmin). Envía solo `complimentary_end` ("YYYY-MM-DD", la misma
 * semántica de fin exclusivo que el alta) y `reason`. Sin estado optimista:
 * tras el 200 refresca la query de consumo (compartida con el checklist de
 * preparación) y el detalle comercial del servidor.
 */
export function ReceptionValidityExtension({ businessId, businessName, subscription }: Props) {
    const router = useRouter();
    const queryClient = useQueryClient();
    const currentEnd = dateStringFromTimestampAR(subscription.current_period_end);
    const minEnd = currentEnd ? addDaysToDateString(currentEnd, 1) : undefined;

    const [open, setOpen] = useState(false);
    const [end, setEnd] = useState('');
    const [reason, setReason] = useState('');
    const [errors, setErrors] = useState<FieldErrors>({});
    const [failure, setFailure] = useState<Failure | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    const [pending, setPending] = useState(false);
    const pendingRef = useRef(false);

    const tier = aiUsageTierLabel(subscription.usage_tier);
    const plan = `Recepcionista IA${tier ? ` · ${tier}` : ''}`;

    const openModal = () => {
        setEnd(currentEnd ? addCalendarMonths(currentEnd, 1) : '');
        setReason('');
        setErrors({});
        setFailure(null);
        setSuccess(null);
        setOpen(true);
    };

    const close = () => {
        if (pendingRef.current) return;
        setOpen(false);
    };

    const validate = (): FieldErrors => {
        const result: FieldErrors = {};
        if (!end) result.complimentary_end = 'Elegí la nueva fecha de vencimiento.';
        else if (!currentEnd || end <= currentEnd) result.complimentary_end = 'Tiene que ser posterior al vencimiento actual.';
        const trimmed = reason.trim();
        if (!trimmed) result.reason = 'Indicá el motivo de la extensión.';
        else if (trimmed.length > EXTENSION_REASON_MAX) result.reason = `Máximo ${EXTENSION_REASON_MAX} caracteres.`;
        return result;
    };

    const refreshCommercialData = async () => {
        // Misma query que lee el checklist de preparación; el detalle comercial es del servidor.
        await queryClient.invalidateQueries({ queryKey: adminAIUsageKey(businessId) });
        router.refresh();
    };

    const submit = async () => {
        if (pendingRef.current) return;
        const found = validate();
        setErrors(found);
        setFailure(null);
        if (found.complimentary_end || found.reason) return;
        pendingRef.current = true;
        setPending(true);
        try {
            const response = await extendAdminReceptionSubscription(businessId, subscription.id, {
                complimentary_end: end,
                reason: reason.trim(),
            });
            pendingRef.current = false;
            setOpen(false);
            setSuccess(`Vigencia extendida hasta el ${formatDateFromTimestampAR(response.extension.new_end)}.`);
            await refreshCommercialData();
        } catch (error) {
            const result = extensionFailure(error);
            setFailure(result);
            if (result.fields) setErrors(result.fields);
        } finally {
            pendingRef.current = false;
            setPending(false);
        }
    };

    const reload = async () => {
        setOpen(false);
        setFailure(null);
        await refreshCommercialData();
    };

    return (
        <div className="space-y-2">
            <Button type="button" variant="outline" size="sm" onClick={openModal}>
                Extender vigencia
            </Button>
            {success ? <p className="text-xs text-emerald-700" role="status">{success}</p> : null}

            <Modal
                open={open}
                title="Extender vigencia"
                eyebrow={null}
                onClose={close}
                footer={
                    <div className="flex justify-end gap-2">
                        <Button type="button" variant="outline" disabled={pending} onClick={close}>
                            Cancelar
                        </Button>
                        <Button type="button" disabled={pending} onClick={submit}>
                            {pending ? 'Extendiendo…' : 'Extender vigencia'}
                        </Button>
                    </div>
                }
            >
                <dl className="grid gap-2 text-sm sm:grid-cols-2">
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-400">Comercio</dt>
                        <dd className="font-medium text-slate-800">{businessName}</dd>
                    </div>
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-400">Plan contratado</dt>
                        <dd className="text-slate-700">{plan}</dd>
                    </div>
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-400">Vencimiento actual</dt>
                        <dd className="text-slate-700">{formatDateFromTimestampAR(subscription.current_period_end)}</dd>
                    </div>
                </dl>

                <fieldset disabled={pending} className="mt-4 space-y-3">
                    <div className="text-sm font-medium text-slate-700">
                        <span aria-hidden="true">Nueva fecha de vencimiento</span>
                        <DatePicker
                            label="Nueva fecha de vencimiento"
                            value={end}
                            onChange={(value) => {
                                setEnd(value);
                                setErrors((prev) => ({ ...prev, complimentary_end: undefined }));
                            }}
                            today={todayDateString()}
                            min={minEnd}
                            triggerClassName="mt-1 py-2 font-normal"
                            sheetTitle="Nueva fecha de vencimiento"
                        />
                        <p className="mt-1 text-xs font-normal text-slate-500">
                            Igual que en el alta: la bonificación termina al comenzar ese día (hora de Argentina).
                        </p>
                        {errors.complimentary_end ? (
                            <p className="mt-1 text-xs font-normal text-rose-700">{errors.complimentary_end}</p>
                        ) : null}
                    </div>
                    <div>
                        <label htmlFor="extension-reason" className="block text-sm font-medium text-slate-700">
                            Motivo
                        </label>
                        <textarea
                            id="extension-reason"
                            value={reason}
                            maxLength={EXTENSION_REASON_MAX}
                            onChange={(event) => {
                                setReason(event.target.value);
                                setErrors((prev) => ({ ...prev, reason: undefined }));
                            }}
                            rows={3}
                            aria-invalid={Boolean(errors.reason)}
                            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                        />
                        <p className="mt-1 text-xs text-slate-500">{reason.trim().length}/{EXTENSION_REASON_MAX}</p>
                        {errors.reason ? <p className="mt-1 text-xs text-rose-700">{errors.reason}</p> : null}
                    </div>
                </fieldset>
                <div className="mt-3 space-y-3">
                    <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                        Extender la vigencia no reinicia el consumo del período, no cambia el cupo contratado y no
                        modifica la atención automática.
                    </p>
                    {failure ? (
                        <div className="text-xs text-rose-700" role="alert">
                            <p>{failure.text}</p>
                            {failure.reload ? (
                                <Button type="button" variant="outline" size="sm" className="mt-2" onClick={reload}>
                                    Recargar datos
                                </Button>
                            ) : null}
                        </div>
                    ) : null}
                </div>
            </Modal>
        </div>
    );
}
