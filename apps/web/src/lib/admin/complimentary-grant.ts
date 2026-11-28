/**
 * PROD-09E — Commercial fields of a complimentary ("bonificado") grant,
 * shared by the "Nuevo cliente" form (ADMIN-CLIENTES 03C / PROD-02F3) and the
 * "Agregar Recepcionista IA" modal (PROD-02F5 add-service). Same messages and
 * rules in both; the backend keeps the final authority.
 *
 * Dates are plain "YYYY-MM-DD" strings (never routed through `Date`): the
 * backend parses a bare date as 00:00 in its TIME_ZONE, with an exclusive end.
 */
import type { AdminProvisioningPlanOption, AdminProvisioningUsageTierOption } from './types';

export type ComplimentaryGrantFields = {
  plan_code: string;
  usage_tier: string;
  custom_included_sessions: string;
  complimentary_start: string;
  complimentary_end: string;
  grant_reason: string;
};

export type ComplimentaryGrantErrors = Partial<Record<keyof ComplimentaryGrantFields, string>>;

/** `custom_allowance` of the selected tier (Recepcionista Custom), or null. */
export function customAllowanceOf(
  plan: AdminProvisioningPlanOption | null,
  usageTier: string,
): NonNullable<AdminProvisioningUsageTierOption['custom_allowance']> | null {
  return plan?.usage_tiers?.find((tier) => tier.code === usageTier)?.custom_allowance ?? null;
}

export function validateComplimentaryGrant(
  form: ComplimentaryGrantFields,
  selectedPlan: AdminProvisioningPlanOption | null,
): ComplimentaryGrantErrors {
  const errors: ComplimentaryGrantErrors = {};

  if (!form.plan_code) {
    errors.plan_code = 'Seleccioná un plan.';
  }
  if (selectedPlan?.usage_tiers?.length && !form.usage_tier) {
    errors.usage_tier = 'Seleccioná el nivel de uso.';
  }
  const customAllowance = customAllowanceOf(selectedPlan, form.usage_tier);
  if (customAllowance) {
    const raw = form.custom_included_sessions.trim();
    const value = Number(raw);
    if (!/^\d+$/.test(raw) || !Number.isSafeInteger(value) || value < customAllowance.min || value > customAllowance.max) {
      errors.custom_included_sessions = `Ingresá un número entero entre ${customAllowance.min} y ${customAllowance.max.toLocaleString('es-AR')}.`;
    }
  }

  if (!form.complimentary_start) {
    errors.complimentary_start = 'Ingresá la fecha de inicio.';
  }
  if (!form.complimentary_end) {
    errors.complimentary_end = 'Ingresá la fecha de fin.';
  } else if (form.complimentary_start && form.complimentary_end <= form.complimentary_start) {
    errors.complimentary_end = 'Debe ser posterior a la fecha de inicio.';
  }

  if (!form.grant_reason.trim()) {
    errors.grant_reason = 'Ingresá el motivo de la bonificación.';
  }

  return errors;
}

/**
 * Tier-dependent payload fields, exactly as the alta sends them: `usage_tier`
 * only for tier-priced plans, `custom_included_sessions` only for a tier with
 * `custom_allowance`.
 */
export function usageTierPayload(
  form: ComplimentaryGrantFields,
  selectedPlan: AdminProvisioningPlanOption | null,
): { usage_tier?: string; custom_included_sessions?: number } {
  const tiers = selectedPlan?.usage_tiers ?? [];
  return {
    ...(tiers.length > 0 ? { usage_tier: form.usage_tier } : {}),
    ...(customAllowanceOf(selectedPlan, form.usage_tier)
      ? { custom_included_sessions: Number(form.custom_included_sessions.trim()) }
      : {}),
  };
}
