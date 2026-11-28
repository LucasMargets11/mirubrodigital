'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

import { ToastBubble } from '@/components/app/toast';
import {
  ComplimentaryPeriodFields,
  GrantReasonField,
  UsageTierFields,
  errorClass,
  inputClass,
  labelClass,
} from '@/components/admin/complimentary-grant-fields';
import {
  getAdminClientProvisioningOptions,
  provisionAdminClient,
} from '@/lib/admin/client';
import { customAllowanceOf, usageTierPayload, validateComplimentaryGrant } from '@/lib/admin/complimentary-grant';
import { todayDateOnly } from '@/lib/admin/complimentary-period';
import type {
  AdminClientProvisioningOptions,
  AdminClientProvisioningResult,
  AdminProvisioningPlanOption,
} from '@/lib/admin/types';

type FormState = {
  business_name: string;
  business_slug: string;
  service_type: string;
  plan_code: string;
  usage_tier: string;
  custom_included_sessions: string;
  country: string;
  currency: string;
  owner_email: string;
  complimentary_start: string;
  complimentary_end: string;
  grant_reason: string;
};

const INITIAL_FORM: FormState = {
  business_name: '',
  business_slug: '',
  service_type: '',
  plan_code: '',
  usage_tier: '',
  custom_included_sessions: '',
  country: 'AR',
  currency: 'ARS',
  owner_email: '',
  complimentary_start: todayDateOnly(),
  complimentary_end: '',
  grant_reason: '',
};

type OptionsState = 'loading' | 'ready' | 'error';

/**
 * PROD-02F4: a pending confirmation to reuse an existing account as owner.
 * Bound to the exact (normalized) email it was issued for; `renewed` marks a
 * prompt re-issued because the identified account changed.
 */
type OwnerConfirmation = { token: string; email: string; renewed: boolean };

const OWNER_CONFIRMATION_CODES = new Set([
  'existing_owner_requires_confirmation',
  'existing_owner_confirmation_invalid',
]);

function normalizeEmail(value: string): string {
  return value.trim().toLowerCase();
}
const FIELD_ORDER: (keyof FormState)[] = [
  'business_name',
  'business_slug',
  'owner_email',
  'service_type',
  'plan_code',
  'usage_tier',
  'custom_included_sessions',
  'country',
  'currency',
  'complimentary_start',
  'complimentary_end',
  'grant_reason',
];

function validate(
  form: FormState,
  selectedPlan: AdminProvisioningPlanOption | null,
): Partial<Record<keyof FormState, string>> {
  const errors: Partial<Record<keyof FormState, string>> = {};

  if (!form.business_name.trim()) {
    errors.business_name = 'El nombre del negocio es obligatorio.';
  }

  const slug = form.business_slug.trim();
  if (!slug) {
    errors.business_slug = 'El slug es obligatorio.';
  } else if (!/^[a-z0-9-]+$/.test(slug)) {
    errors.business_slug = 'Solo minúsculas, números y guiones (-). Sin espacios.';
  } else if (slug.length > 80) {
    errors.business_slug = 'El slug no puede superar los 80 caracteres.';
  }

  const email = form.owner_email.trim();
  if (!email) {
    errors.owner_email = 'El email del owner es obligatorio.';
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errors.owner_email = 'Ingresá un email válido.';
  }

  if (!form.service_type) {
    errors.service_type = 'Seleccioná un servicio.';
  }

  const country = form.country.trim();
  if (!country || country.length > 2) {
    errors.country = 'El país debe tener hasta 2 caracteres.';
  }
  const currency = form.currency.trim();
  if (!currency || currency.length > 3) {
    errors.currency = 'La moneda debe tener hasta 3 caracteres.';
  }

  // Plan, nivel de uso, cupo, período y motivo: reglas compartidas (PROD-09E).
  return { ...errors, ...validateComplimentaryGrant(form, selectedPlan) };
}

export function NuevoClienteForm() {
  const router = useRouter();

  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [serverError, setServerError] = useState('');
  const [provisionedClient, setProvisionedClient] = useState<AdminClientProvisioningResult | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<{
    message: string;
    tone: 'success' | 'error';
  } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [accessDenied, setAccessDenied] = useState(false);
  const [ownerConfirmation, setOwnerConfirmation] = useState<OwnerConfirmation | null>(null);
  const confirmButtonRef = useRef<HTMLButtonElement | null>(null);

  const [optionsState, setOptionsState] = useState<OptionsState>('loading');
  const [options, setOptions] = useState<AdminClientProvisioningOptions | null>(null);

  const fieldRefs = useRef<Record<keyof FormState, HTMLElement | null>>(
    {} as Record<keyof FormState, HTMLElement | null>,
  );
  // Synchronous guard against double-click/double-Enter — independent of
  // React state batching timing (the `submitting` state alone isn't enough:
  // two synchronous clicks in the same tick both close over the same stale
  // `submitting = false`).
  const submittingRef = useRef(false);

  const loadOptions = useCallback(async () => {
    setOptionsState('loading');
    const result = await getAdminClientProvisioningOptions();
    if (result.status === 'ok') {
      setOptions(result.data);
      setOptionsState('ready');
    } else if (result.status === 'session_expired') {
      window.location.assign('/admin/login');
    } else {
      setOptionsState('error');
    }
  }, []);

  useEffect(() => {
    loadOptions();
  }, [loadOptions]);

  const selectedService = options?.services.find((svc) => svc.value === form.service_type) ?? null;
  const availablePlans: AdminProvisioningPlanOption[] = selectedService?.plans ?? [];
  const selectedPlan = availablePlans.find((plan) => plan.code === form.plan_code) ?? null;
  const usageTiers = selectedPlan?.usage_tiers ?? [];
  const customAllowance = customAllowanceOf(selectedPlan, form.usage_tier);

  function handleServiceChange(value: string) {
    setForm((f) => {
      const svc = options?.services.find((s) => s.value === value);
      const plans = svc?.plans ?? [];
      const planStillValid = plans.some((p) => p.code === f.plan_code);
      return planStillValid
        ? { ...f, service_type: value }
        : { ...f, service_type: value, plan_code: '', usage_tier: '', custom_included_sessions: '' };
    });
  }

  function handlePlanChange(value: string) {
    setForm((f) => {
      const plan = availablePlans.find((p) => p.code === value);
      const tierStillValid = (plan?.usage_tiers ?? []).some((t) => t.code === f.usage_tier);
      return tierStillValid
        ? { ...f, plan_code: value }
        : { ...f, plan_code: value, usage_tier: '', custom_included_sessions: '' };
    });
  }

  function handleChange<K extends keyof FormState>(key: K, value: string) {
    // A confirmation is valid only for the email it was issued for (PROD-02F4)
    if (key === 'owner_email') {
      setOwnerConfirmation(null);
    }
    // A different tier never keeps the previous custom allowance (PROD-02F3)
    setForm((f) => (key === 'usage_tier' && value !== f.usage_tier
      ? { ...f, usage_tier: value, custom_included_sessions: '' }
      : { ...f, [key]: value }));
  }

  const grantFieldProps = {
    form,
    errors,
    onChange: (key: keyof FormState, value: string) => handleChange(key, value),
    registerRef: (key: keyof FormState, el: HTMLElement | null) => {
      fieldRefs.current[key] = el;
    },
  };

  function focusFirstInvalid(errs: Partial<Record<keyof FormState, string>>) {
    const firstKey = FIELD_ORDER.find((key) => errs[key]);
    if (firstKey) {
      fieldRefs.current[firstKey]?.focus();
    }
  }

  async function handleCopyInstructions() {
    if (!provisionedClient) return;

    const instructions = `Tu acceso a Mi Rubro está habilitado.\n\nIngresá con Google usando esta cuenta:\n${provisionedClient.owner_email}\n\nAcceso:\n${provisionedClient.login_url}`;

    try {
      await navigator.clipboard.writeText(instructions);
      setCopyFeedback({ message: 'Instrucciones copiadas correctamente.', tone: 'success' });
    } catch {
      setCopyFeedback({
        message: 'No se pudieron copiar las instrucciones. Intentá nuevamente.',
        tone: 'error',
      });
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    void submitProvisioning(null);
  }

  function handleUseAnotherEmail() {
    setOwnerConfirmation(null);
    fieldRefs.current.owner_email?.focus();
  }

  async function submitProvisioning(confirmation: OwnerConfirmation | null) {
    if (submittingRef.current) return;
    // Never send a confirmation issued for a different email than the current one.
    const confirmed = confirmation && confirmation.email === normalizeEmail(form.owner_email) ? confirmation : null;

    const validationErrors = validate(form, selectedPlan);
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) {
      focusFirstInvalid(validationErrors);
      return;
    }

    submittingRef.current = true;
    setSubmitting(true);
    setServerError('');

    try {
      const response = await provisionAdminClient({
        business_name: form.business_name.trim(),
        business_slug: form.business_slug.trim(),
        service_type: form.service_type,
        country: form.country.trim().toUpperCase(),
        currency: form.currency.trim().toUpperCase(),
        owner_email: form.owner_email.trim(),
        plan_code: form.plan_code,
        complimentary_start: form.complimentary_start,
        complimentary_end: form.complimentary_end,
        grant_reason: form.grant_reason.trim(),
        ...usageTierPayload(form, selectedPlan),
        ...(confirmed ? { attach_existing_owner: true as const, owner_confirmation_token: confirmed.token } : {}),
      });

      switch (response.status) {
        case 'ok': {
          setOwnerConfirmation(null);
          setProvisionedClient(response.data);
          return;
        }
        case 'session_expired':
          window.location.assign('/admin/login');
          return;
        case 'forbidden':
          setAccessDenied(true);
          return;
        case 'domain_error': {
          const { error } = response;
          if (OWNER_CONFIRMATION_CODES.has(error.code) && error.confirmation) {
            setErrors((prev) => ({ ...prev, owner_email: undefined }));
            setOwnerConfirmation({
              token: error.confirmation.token,
              email: normalizeEmail(error.confirmation.owner_email),
              renewed: error.code === 'existing_owner_confirmation_invalid',
            });
            setTimeout(() => confirmButtonRef.current?.focus(), 0);
            return;
          }
          setOwnerConfirmation(null);
          if (error.field && (FIELD_ORDER as string[]).includes(error.field)) {
            setErrors((prev) => ({ ...prev, [error.field as keyof FormState]: error.detail }));
            fieldRefs.current[error.field as keyof FormState]?.focus();
          } else {
            setServerError(error.detail || 'No se pudo completar el alta. Revisá los datos e intentá de nuevo.');
          }
          return;
        }
        case 'field_errors': {
          const mapped: Partial<Record<keyof FormState, string>> = {};
          for (const [key, message] of Object.entries(response.fieldErrors)) {
            if ((FIELD_ORDER as string[]).includes(key)) {
              mapped[key as keyof FormState] = message;
            }
          }
          setErrors((prev) => ({ ...prev, ...mapped }));
          focusFirstInvalid(mapped);
          if (Object.keys(mapped).length === 0) {
            setServerError('No se pudo completar el alta. Revisá los datos e intentá de nuevo.');
          }
          return;
        }
        case 'server_error':
        default:
          setServerError('Ocurrió un error inesperado. Intentá de nuevo en unos minutos.');
          return;
      }
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  if (accessDenied) {
    return (
      <div className="rounded-md bg-red-50 px-4 py-6 text-sm text-red-700">
        <p className="font-medium">No tenés permisos para provisionar clientes.</p>
        <Link href="/admin/clientes" className="mt-2 inline-block text-red-800 underline">
          Volver a Clientes
        </Link>
      </div>
    );
  }

  if (provisionedClient) {
    return (
      <div className="max-w-3xl space-y-6">
        {copyFeedback && (
          <ToastBubble message={copyFeedback.message} tone={copyFeedback.tone} />
        )}

        <section
          className="rounded-xl border border-emerald-200 bg-white p-6 shadow-sm"
          aria-labelledby="client-created-title"
        >
          <p className="text-sm font-semibold text-emerald-700">Alta completada</p>
          <h2 id="client-created-title" className="mt-1 text-2xl font-semibold text-slate-950">
            Cliente creado correctamente
          </h2>

          <dl className="mt-6 grid gap-4 rounded-lg bg-slate-50 p-4 sm:grid-cols-2">
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Negocio</dt>
              <dd className="mt-1 text-base font-semibold text-slate-900">
                {provisionedClient.business.name}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Cuenta del propietario
              </dt>
              <dd className="mt-1 break-all text-base font-semibold text-slate-900">
                {provisionedClient.owner_email}
              </dd>
            </div>
          </dl>

          <div className="mt-6 space-y-2 text-sm text-slate-700">
            {!provisionedClient.owner.created && (
              <p>Se asoció una cuenta existente: conserva su contraseña, su perfil y sus accesos actuales.</p>
            )}
            <p className="font-medium text-slate-900">
              El propietario debe ingresar con esta misma cuenta de Google
            </p>
            <p>No se generó una contraseña ni se envió un email automáticamente</p>
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={handleCopyInstructions}
              className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Copiar instrucciones
            </button>
            <a
              href={provisionedClient.login_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
            >
              Ingresar con Google
            </a>
            <button
              type="button"
              onClick={() => router.push(`/admin/clientes/${provisionedClient.business_id}`)}
              className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Ver cliente
            </button>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="max-w-3xl space-y-6">
      <form onSubmit={handleSubmit} className="space-y-6" noValidate>
        {serverError && (
          <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
            {serverError}
          </div>
        )}

        {/* ── Negocio ─────────────────────────────────────────────────── */}
        <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-4">
          <h2 className="text-sm font-semibold text-slate-900">Negocio</h2>

          <div>
            <label htmlFor="business_name" className={labelClass}>
              Nombre del negocio
            </label>
            <input
              id="business_name"
              ref={(el) => {
                fieldRefs.current.business_name = el;
              }}
              value={form.business_name}
              onChange={(e) => handleChange('business_name', e.target.value)}
              aria-invalid={Boolean(errors.business_name)}
              aria-describedby={errors.business_name ? 'business_name-error' : undefined}
              className={inputClass}
            />
            {errors.business_name && (
              <p id="business_name-error" className={errorClass}>{errors.business_name}</p>
            )}
          </div>

          <div>
            <label htmlFor="business_slug" className={labelClass}>
              Slug
            </label>
            <input
              id="business_slug"
              ref={(el) => {
                fieldRefs.current.business_slug = el;
              }}
              value={form.business_slug}
              onChange={(e) => handleChange('business_slug', e.target.value)}
              aria-invalid={Boolean(errors.business_slug)}
              aria-describedby="business_slug-help business_slug-error"
              className={`${inputClass} font-mono`}
            />
            <p id="business_slug-help" className="mt-1 text-xs text-slate-500">
              Solo minúsculas, números y guiones (-). Sin espacios. Máximo 80 caracteres.
            </p>
            {errors.business_slug && (
              <p id="business_slug-error" className={errorClass}>{errors.business_slug}</p>
            )}
          </div>
        </div>

        {/* ── Owner ───────────────────────────────────────────────────── */}
        <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-4">
          <h2 className="text-sm font-semibold text-slate-900">Owner</h2>

          <div>
            <label htmlFor="owner_email" className={labelClass}>
              Email del owner
            </label>
            <input
              id="owner_email"
              type="email"
              ref={(el) => {
                fieldRefs.current.owner_email = el;
              }}
              value={form.owner_email}
              onChange={(e) => handleChange('owner_email', e.target.value)}
              aria-invalid={Boolean(errors.owner_email)}
              aria-describedby="owner_email-help owner_email-error"
              className={inputClass}
            />
            <p id="owner_email-help" className="mt-1 text-xs text-slate-500">
              El alta no envía credenciales ni vincula todavía una cuenta de Google.
            </p>
            {errors.owner_email && (
              <p id="owner_email-error" className={errorClass}>{errors.owner_email}</p>
            )}
          </div>

          {ownerConfirmation && (
            <div
              role="group"
              aria-labelledby="owner-confirmation-title"
              aria-describedby="owner-confirmation-body"
              className="space-y-3 rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900"
            >
              <p id="owner-confirmation-title" className="font-semibold">
                Ya existe una cuenta con este email
              </p>
              <div id="owner-confirmation-body" className="space-y-2">
                {ownerConfirmation.renewed && (
                  <p>
                    La cuenta identificada cambió desde la confirmación anterior. Revisá el email y volvé a confirmar.
                  </p>
                )}
                <p>
                  Si confirmás, la cuenta <span className="break-all font-medium">{ownerConfirmation.email}</span>{' '}
                  será la propietaria del nuevo cliente. Conserva su contraseña, su perfil y sus accesos actuales:
                  solo se le agrega este negocio.
                </p>
                <p>Confirmá únicamente si sabés que esa cuenta pertenece a este cliente.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  ref={confirmButtonRef}
                  onClick={() => void submitProvisioning(ownerConfirmation)}
                  disabled={submitting}
                  className="rounded-md bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-60"
                >
                  Asociar cuenta existente y crear cliente
                </button>
                <button
                  type="button"
                  onClick={handleUseAnotherEmail}
                  className="rounded-md border border-amber-300 bg-white px-4 py-2 text-sm font-medium text-amber-900 hover:bg-amber-100"
                >
                  Usar otro email
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ── Servicio y plan ─────────────────────────────────────────── */}
        <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-4">
          <h2 className="text-sm font-semibold text-slate-900">Servicio y plan</h2>

          {optionsState === 'loading' && (
            <p className="text-sm text-slate-500">Cargando servicios y planes disponibles…</p>
          )}

          {optionsState === 'error' && (
            <div className="flex items-center justify-between gap-3 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
              <span>No pudimos cargar los servicios y planes disponibles.</span>
              <button
                type="button"
                onClick={loadOptions}
                className="rounded-md border border-red-300 px-3 py-1 font-medium hover:bg-red-100"
              >
                Reintentar
              </button>
            </div>
          )}

          {optionsState === 'ready' && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="service_type" className={labelClass}>
                  Servicio
                </label>
                <select
                  id="service_type"
                  ref={(el) => {
                    fieldRefs.current.service_type = el;
                  }}
                  value={form.service_type}
                  onChange={(e) => handleServiceChange(e.target.value)}
                  aria-invalid={Boolean(errors.service_type)}
                  className={inputClass}
                >
                  <option value="">Seleccioná un servicio</option>
                  {options?.services.map((svc) => (
                    <option key={svc.value} value={svc.value}>{svc.label}</option>
                  ))}
                </select>
                {errors.service_type && <p className={errorClass}>{errors.service_type}</p>}
              </div>

              <div>
                <label htmlFor="plan_code" className={labelClass}>
                  Plan
                </label>
                <select
                  id="plan_code"
                  ref={(el) => {
                    fieldRefs.current.plan_code = el;
                  }}
                  value={form.plan_code}
                  onChange={(e) => handlePlanChange(e.target.value)}
                  disabled={!form.service_type || availablePlans.length === 0}
                  aria-invalid={Boolean(errors.plan_code)}
                  className={inputClass}
                >
                  <option value="">Seleccioná un plan</option>
                  {availablePlans.map((plan) => (
                    <option key={plan.code} value={plan.code}>{plan.name}</option>
                  ))}
                </select>
                {errors.plan_code && <p className={errorClass}>{errors.plan_code}</p>}
              </div>

              <UsageTierFields {...grantFieldProps} usageTiers={usageTiers} customAllowance={customAllowance} />
            </div>
          )}
        </div>

        {/* ── País y moneda ───────────────────────────────────────────── */}
        <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-4">
          <h2 className="text-sm font-semibold text-slate-900">País y moneda</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="country" className={labelClass}>
                País
              </label>
              <input
                id="country"
                ref={(el) => {
                  fieldRefs.current.country = el;
                }}
                value={form.country}
                maxLength={2}
                onChange={(e) => handleChange('country', e.target.value.toUpperCase())}
                aria-invalid={Boolean(errors.country)}
                className={`${inputClass} uppercase`}
              />
              {errors.country && <p className={errorClass}>{errors.country}</p>}
            </div>
            <div>
              <label htmlFor="currency" className={labelClass}>
                Moneda
              </label>
              <input
                id="currency"
                ref={(el) => {
                  fieldRefs.current.currency = el;
                }}
                value={form.currency}
                maxLength={3}
                onChange={(e) => handleChange('currency', e.target.value.toUpperCase())}
                aria-invalid={Boolean(errors.currency)}
                className={`${inputClass} uppercase`}
              />
              {errors.currency && <p className={errorClass}>{errors.currency}</p>}
            </div>
          </div>
        </div>

        {/* ── Período bonificado ──────────────────────────────────────── */}
        <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-4">
          <h2 className="text-sm font-semibold text-slate-900">Período bonificado</h2>

          <ComplimentaryPeriodFields {...grantFieldProps} />
        </div>

        {/* ── Motivo ──────────────────────────────────────────────────── */}
        <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-4">
          <h2 className="text-sm font-semibold text-slate-900">Motivo</h2>
          <GrantReasonField {...grantFieldProps} />
        </div>

        {/* ── Acciones ────────────────────────────────────────────────── */}
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
          >
            {submitting ? 'Creando…' : 'Crear cliente'}
          </button>
          <Link
            href="/admin/clientes"
            className="rounded-md border border-slate-300 bg-white px-5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Cancelar
          </Link>
        </div>
      </form>
    </div>
  );
}
