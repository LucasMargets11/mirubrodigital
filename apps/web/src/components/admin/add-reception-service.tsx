'use client';

import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';

import {
  ComplimentaryPeriodFields,
  GrantReasonField,
  UsageTierFields,
  errorClass,
  inputClass,
  labelClass,
} from '@/components/admin/complimentary-grant-fields';
import { SectionCard } from '@/components/admin/section-card';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { adminAIUsageKey, useAdminAIUsage } from '@/features/reception/hooks';
import { receptionistConfigAdapter } from '@/features/reception/receptionist-config-api';
import type { AdminAIUsageOverview } from '@/features/reception/types';
import { addServiceToAdminClient, getAdminClientProvisioningOptions } from '@/lib/admin/client';
import {
  type ComplimentaryGrantErrors,
  type ComplimentaryGrantFields,
  customAllowanceOf,
  usageTierPayload,
  validateComplimentaryGrant,
} from '@/lib/admin/complimentary-grant';
import { todayDateOnly } from '@/lib/admin/complimentary-period';
import type { AdminProvisioningPlanOption } from '@/lib/admin/types';

const RECEPTION_SERVICE = 'reception';
/** `SubscriptionV2.manual_grant_reason` y la política Custom: 255 caracteres. */
export const GRANT_REASON_MAX = 255;
/** Mismos estados que acepta PROD-02F5 (`ELIGIBLE_BUSINESS_STATUSES`). */
const ELIGIBLE_STATUSES = new Set(['active', 'trialing']);

/** Turnos IA no cancelado: incompatible con Recepcionista (PROD-02F5, ambos sentidos). */
export function hasActiveTurnosIA(overview: AdminAIUsageOverview | null | undefined): boolean {
  if (!overview) return false;
  const candidates = Array.isArray(overview.diagnosis?.candidates) ? overview.diagnosis.candidates : [];
  const fromCandidates = candidates.some((c) => {
    const candidate = c as { product?: unknown; status?: unknown };
    return candidate.product === 'appointments_ai' && candidate.status !== 'canceled';
  });
  const source = overview.source_subscription;
  const fromSource = source?.product === 'appointments_ai' && source.status !== 'canceled';
  return fromCandidates || fromSource;
}

type Notice = { text: string; reload?: boolean };

/** Errores de dominio que indican datos comerciales desactualizados: recarga explícita. */
const STALE_CODES = new Set([
  'active_complimentary_subscription_conflict',
  'incompatible_ai_service',
  'client_status_not_eligible',
  'client_not_found',
]);

const FIELDS: (keyof ComplimentaryGrantFields)[] = [
  'plan_code',
  'usage_tier',
  'custom_included_sessions',
  'complimentary_start',
  'complimentary_end',
  'grant_reason',
];

const initialForm = (plan: string): ComplimentaryGrantFields => ({
  plan_code: plan,
  usage_tier: '',
  custom_included_sessions: '',
  complimentary_start: todayDateOnly(),
  complimentary_end: '',
  grant_reason: '',
});

type Props = { businessId: number; businessName: string; clientStatus: string };

/**
 * PROD-09E — «Agregar Recepcionista IA» a un comercio existente (superadmin).
 * Se muestra solo cuando la configuración admin respondió 404
 * `client_not_found` (sin Recepcionista no cancelada, principal o
 * adicional). Reutiliza los campos y validaciones del alta y el endpoint
 * PROD-02F5; no toca owner, usuarios, servicio principal ni otras
 * suscripciones. Tras el 201 refresca la configuración (aparece el bloque
 * completo de Recepcionista) y el detalle comercial.
 */
export function AddReceptionServiceSection({ businessId, businessName, clientStatus }: Props) {
  const usage = useAdminAIUsage(businessId);
  const [open, setOpen] = useState(false);

  const eligible = ELIGIBLE_STATUSES.has(clientStatus);
  const turnosIA = hasActiveTurnosIA(usage.data);
  let blocker: ReactNode = null;
  if (!eligible) {
    blocker = `El estado del cliente («${clientStatus}») no permite agregar servicios. No se reactiva ni se cambia su estado.`;
  } else if (usage.isLoading) {
    blocker = 'Verificando los servicios de IA del cliente…';
  } else if (usage.isError) {
    blocker = (
      <>
        No pudimos verificar los servicios de IA del cliente.{' '}
        <Button type="button" variant="outline" size="sm" onClick={() => void usage.refetch()}>
          Reintentar
        </Button>
      </>
    );
  } else if (turnosIA) {
    blocker = 'El cliente tiene Turnos IA: Recepcionista IA y Turnos IA no pueden estar activos en el mismo negocio.';
  }

  return (
    <SectionCard
      title="Recepcionista IA"
      description="El cliente no tiene Recepcionista IA. Se puede agregar como servicio adicional bonificado, sin cambiar su servicio principal."
    >
      {blocker ? (
        <p className="text-sm text-slate-600">{blocker}</p>
      ) : (
        <Button type="button" onClick={() => setOpen(true)}>
          Agregar Recepcionista IA
        </Button>
      )}
      {open && !blocker ? (
        <AddReceptionModal businessId={businessId} businessName={businessName} onClose={() => setOpen(false)} />
      ) : null}
    </SectionCard>
  );
}

type OptionsState =
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'ready'; plans: AdminProvisioningPlanOption[] };

function AddReceptionModal({ businessId, businessName, onClose }: {
  businessId: number;
  businessName: string;
  onClose: () => void;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [options, setOptions] = useState<OptionsState>({ kind: 'loading' });
  const [form, setForm] = useState<ComplimentaryGrantFields>(initialForm(''));
  const [errors, setErrors] = useState<ComplimentaryGrantErrors>({});
  const [notice, setNotice] = useState<Notice | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const fieldRefs = useRef<Partial<Record<keyof ComplimentaryGrantFields, HTMLElement | null>>>({});

  const loadOptions = useCallback(async () => {
    setOptions({ kind: 'loading' });
    const result = await getAdminClientProvisioningOptions();
    if (result.status === 'session_expired') {
      window.location.assign('/admin/login');
      return;
    }
    if (result.status !== 'ok') {
      setOptions({ kind: 'error' });
      return;
    }
    const plans = result.data.services.find((svc) => svc.value === RECEPTION_SERVICE)?.plans ?? [];
    setOptions({ kind: 'ready', plans });
    // Un único plan de Recepcionista: queda elegido (nunca se pide otro dato comercial).
    if (plans.length === 1) setForm((f) => ({ ...f, plan_code: f.plan_code || plans[0].code }));
  }, []);

  useEffect(() => {
    void loadOptions();
  }, [loadOptions]);

  const plans = options.kind === 'ready' ? options.plans : [];
  const selectedPlan = plans.find((plan) => plan.code === form.plan_code) ?? null;
  const usageTiers = selectedPlan?.usage_tiers ?? [];
  const customAllowance = customAllowanceOf(selectedPlan, form.usage_tier);

  function handleChange(key: keyof ComplimentaryGrantFields, value: string) {
    // Mismo comportamiento que el alta: otro plan o nivel nunca conserva el cupo anterior.
    setForm((f) => {
      if (key === 'plan_code' && value !== f.plan_code) {
        return { ...f, plan_code: value, usage_tier: '', custom_included_sessions: '' };
      }
      if (key === 'usage_tier' && value !== f.usage_tier) {
        return { ...f, usage_tier: value, custom_included_sessions: '' };
      }
      return { ...f, [key]: value };
    });
    setErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  const fieldProps = {
    form,
    errors,
    onChange: handleChange,
    registerRef: (key: keyof ComplimentaryGrantFields, el: HTMLElement | null) => {
      fieldRefs.current[key] = el;
    },
  };

  function focusFirst(errs: ComplimentaryGrantErrors) {
    const first = FIELDS.find((key) => errs[key]);
    if (first) fieldRefs.current[first]?.focus();
  }

  function validate(): ComplimentaryGrantErrors {
    const errs = validateComplimentaryGrant(form, selectedPlan);
    if (!errs.grant_reason && form.grant_reason.trim().length > GRANT_REASON_MAX) {
      errs.grant_reason = `El motivo no puede superar los ${GRANT_REASON_MAX} caracteres.`;
    }
    return errs;
  }

  const close = () => {
    if (submittingRef.current) return;
    onClose();
  };

  async function refreshCommercialData() {
    // La configuración vuelve a leerse: con Recepcionista ya no responde 404 y
    // la tarjeta muestra el bloque completo bajo el mismo Providers.
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: receptionistConfigAdapter({ kind: 'platform_admin', businessId }).key }),
      queryClient.invalidateQueries({ queryKey: adminAIUsageKey(businessId) }),
    ]);
    router.refresh();
  }

  async function submit() {
    if (submittingRef.current || options.kind !== 'ready') return;
    const errs = validate();
    setErrors(errs);
    setNotice(null);
    if (Object.keys(errs).length > 0) {
      focusFirst(errs);
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    try {
      const response = await addServiceToAdminClient(businessId, {
        service_type: RECEPTION_SERVICE,
        plan_code: form.plan_code,
        complimentary_start: form.complimentary_start,
        complimentary_end: form.complimentary_end,
        grant_reason: form.grant_reason.trim(),
        ...usageTierPayload(form, selectedPlan),
      });
      switch (response.status) {
        case 'ok':
          submittingRef.current = false;
          onClose();
          await refreshCommercialData();
          return;
        case 'session_expired':
          window.location.assign('/admin/login');
          return;
        case 'forbidden':
          setNotice({ text: 'Solo un superadmin puede agregar servicios. No se cambió nada.' });
          return;
        case 'domain_error': {
          const { error } = response;
          const field = error.field as keyof ComplimentaryGrantFields | null;
          // Solo en un campo visible (p. ej. sin selector de plan, `plan_code` va al aviso).
          if (field && FIELDS.includes(field) && fieldRefs.current[field] && !STALE_CODES.has(error.code)) {
            setErrors((prev) => ({ ...prev, [field]: error.detail }));
            fieldRefs.current[field]?.focus();
            return;
          }
          setNotice({
            text: `${error.detail || 'No se pudo agregar Recepcionista IA.'} No se cambió nada.`,
            reload: STALE_CODES.has(error.code),
          });
          return;
        }
        case 'field_errors': {
          const mapped: ComplimentaryGrantErrors = {};
          for (const [key, message] of Object.entries(response.fieldErrors)) {
            const field = key as keyof ComplimentaryGrantFields;
            if (FIELDS.includes(field) && fieldRefs.current[field]) mapped[field] = message;
          }
          setErrors((prev) => ({ ...prev, ...mapped }));
          focusFirst(mapped);
          if (Object.keys(mapped).length === 0) {
            setNotice({ text: 'No se pudo agregar Recepcionista IA. Revisá los datos e intentá de nuevo.' });
          }
          return;
        }
        case 'server_error':
        default:
          setNotice({
            text: response.status === 'server_error' && response.httpStatus === 0
              ? 'Error de red: no pudimos contactar a Mi Rubro. No se cambió nada; podés intentarlo nuevamente.'
              : 'Ocurrió un error inesperado. No se cambió nada; intentá de nuevo en unos minutos.',
          });
          return;
      }
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  async function reload() {
    onClose();
    await refreshCommercialData();
  }

  const ready = options.kind === 'ready' && plans.length > 0;

  return (
    <Modal
      open
      title="Agregar Recepcionista IA"
      eyebrow={null}
      onClose={close}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" disabled={submitting} onClick={close}>
            Cancelar
          </Button>
          <Button type="button" disabled={submitting || !ready} onClick={submit}>
            {submitting ? 'Agregando…' : 'Agregar Recepcionista IA'}
          </Button>
        </div>
      }
    >
      <p className="text-sm text-slate-600">
        Comercio: <span className="font-medium text-slate-800">{businessName}</span>
      </p>
      <p className="mt-2 text-xs text-slate-500">
        Se agrega como servicio bonificado. No cambia el servicio principal, el owner, los usuarios ni las
        suscripciones actuales, y no habilita la atención automática ni conecta WhatsApp.
      </p>

      {options.kind === 'loading' ? (
        <p className="mt-4 text-sm text-slate-500">Cargando planes disponibles…</p>
      ) : null}
      {options.kind === 'error' ? (
        <div className="mt-4 flex items-center justify-between gap-3 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
          <span>No pudimos cargar los planes disponibles.</span>
          <Button type="button" variant="outline" size="sm" onClick={() => void loadOptions()}>
            Reintentar
          </Button>
        </div>
      ) : null}
      {options.kind === 'ready' && plans.length === 0 ? (
        <p className="mt-4 text-sm text-amber-800">Recepcionista IA no está disponible para alta interna.</p>
      ) : null}

      {ready ? (
        <fieldset disabled={submitting} className="mt-4 space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {plans.length > 1 ? (
              <div className="sm:col-span-2">
                <label htmlFor="plan_code" className={labelClass}>Plan</label>
                <select
                  id="plan_code"
                  ref={(el) => fieldProps.registerRef('plan_code', el)}
                  value={form.plan_code}
                  onChange={(e) => handleChange('plan_code', e.target.value)}
                  aria-invalid={Boolean(errors.plan_code)}
                  className={inputClass}
                >
                  <option value="">Seleccioná un plan</option>
                  {plans.map((plan) => (
                    <option key={plan.code} value={plan.code}>{plan.name}</option>
                  ))}
                </select>
                {errors.plan_code && <p className={errorClass}>{errors.plan_code}</p>}
              </div>
            ) : null}
            <UsageTierFields {...fieldProps} usageTiers={usageTiers} customAllowance={customAllowance} />
          </div>
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-slate-900">Período bonificado</h3>
            <ComplimentaryPeriodFields {...fieldProps} />
          </div>
          <GrantReasonField {...fieldProps} maxLength={GRANT_REASON_MAX} />
        </fieldset>
      ) : null}

      {notice ? (
        <div className="mt-3 text-sm text-rose-700" role="alert">
          <p>{notice.text}</p>
          {notice.reload ? (
            <Button type="button" variant="outline" size="sm" className="mt-2" onClick={() => void reload()}>
              Recargar datos
            </Button>
          ) : null}
        </div>
      ) : null}
    </Modal>
  );
}
