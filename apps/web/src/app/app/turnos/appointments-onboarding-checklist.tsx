'use client';

import Link from 'next/link';
import { useState } from 'react';

import { useAppointmentOnboardingStatus } from '@/features/appointments/hooks';

const ESSENTIAL_STEPS = [
  {
    key: 'services',
    label: 'Servicios',
    href: '/app/turnos/servicios',
    action: 'Configurar servicios',
  },
  {
    key: 'schedule',
    label: 'Horarios',
    href: '/app/turnos/horarios',
    action: 'Configurar horarios',
  },
  {
    key: 'public_booking',
    label: 'Link público',
    href: '#public-booking-link',
    action: 'Ver link de reservas',
  },
] as const;

export function AppointmentsOnboardingChecklist() {
  const [dismissed, setDismissed] = useState(false);
  const query = useAppointmentOnboardingStatus();

  if (dismissed) return null;

  const status = query.data;
  const completedCount = status
    ? Number(status.has_reservable_service) +
      Number(status.has_valid_availability) +
      Number(status.public_booking_available)
    : 0;
  const progress = Math.round((completedCount / ESSENTIAL_STEPS.length) * 100);

  return (
    <section
      aria-labelledby="turnos-onboarding-title"
      className="space-y-4 rounded-2xl border border-brand-200 bg-brand-50/60 p-4 shadow-sm sm:p-5"
      data-testid="turnos-onboarding-checklist"
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 id="turnos-onboarding-title" className="text-base font-semibold text-slate-900">
            Prepará tu agenda para recibir reservas
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            Configurá lo esencial. Podés hacerlo en cualquier orden y seguir usando Turnos.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="shrink-0 rounded-lg px-2 py-1 text-xs font-medium text-slate-600 hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
          aria-label="Ocultar guía de primeros pasos"
        >
          Ocultar
        </button>
      </header>

      {query.isPending ? (
        <p className="text-sm text-slate-600" role="status">
          Revisando la configuración de Turnos…
        </p>
      ) : query.isError ? (
        <div className="flex flex-wrap items-center gap-3" role="alert">
          <p className="text-sm text-rose-700">No pudimos comprobar el estado de configuración.</p>
          <button
            type="button"
            onClick={() => void query.refetch()}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Volver a intentar
          </button>
        </div>
      ) : status ? (
        <>
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span className="font-medium text-slate-800">
                {completedCount} de {ESSENTIAL_STEPS.length} pasos esenciales completados
              </span>
              <span className="text-slate-600">{progress}%</span>
            </div>
            <div
              role="progressbar"
              aria-label="Progreso de configuración esencial"
              aria-valuemin={0}
              aria-valuemax={ESSENTIAL_STEPS.length}
              aria-valuenow={completedCount}
              className="h-2 overflow-hidden rounded-full bg-white"
            >
              <div
                className="h-full rounded-full bg-brand-600 transition-[width]"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          <ul className="grid gap-3 sm:grid-cols-2">
            {ESSENTIAL_STEPS.map((step) => {
              const ready =
                step.key === 'services'
                  ? status.has_reservable_service
                  : step.key === 'schedule'
                    ? status.has_valid_availability
                    : status.public_booking_available;

              return (
                <li
                  key={step.key}
                  className="flex min-w-0 flex-col justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3 xl:flex-row xl:items-center"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-800">{step.label}</p>
                    <p className={ready ? 'text-xs text-emerald-700' : 'text-xs text-slate-500'}>
                      {ready ? 'Listo' : 'Pendiente'}
                    </p>
                  </div>
                  <Link
                    href={step.href}
                    className="shrink-0 rounded-lg border border-slate-300 px-3 py-1.5 text-center text-sm font-medium text-slate-700 hover:bg-slate-50"
                  >
                    {step.action}
                  </Link>
                </li>
              );
            })}
            <li className="flex min-w-0 flex-col justify-between gap-3 rounded-xl border border-dashed border-slate-300 bg-white/70 p-3 xl:flex-row xl:items-center">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-800">
                  Profesionales <span className="font-normal text-slate-500">(opcional)</span>
                </p>
                <p className="text-xs text-slate-500">
                  {status.active_professionals_count > 0
                    ? `${status.active_professionals_count} activos`
                    : 'Podés agregar profesionales si necesitás agendas separadas.'}
                </p>
              </div>
              <Link
                href="/app/turnos/profesionales"
                className="shrink-0 rounded-lg border border-slate-300 px-3 py-1.5 text-center text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Gestionar profesionales
              </Link>
            </li>
          </ul>

          <div aria-live="polite" className="flex flex-wrap items-center justify-between gap-3">
            <p
              className={
                status.ready_to_receive_bookings
                  ? 'text-sm font-medium text-emerald-800'
                  : 'text-sm text-slate-600'
              }
            >
              {status.ready_to_receive_bookings
                ? 'Tu agenda está lista para recibir reservas.'
                : 'Completá los pasos esenciales para empezar a recibir reservas.'}
            </p>
            {status.ready_to_receive_bookings && (
              <Link
                href="/app/turnos/turnos"
                className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
              >
                Ver agenda
              </Link>
            )}
          </div>
        </>
      ) : null}
    </section>
  );
}
