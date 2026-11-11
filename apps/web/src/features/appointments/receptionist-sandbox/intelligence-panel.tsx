'use client';

import { Check, Circle, Sparkles } from 'lucide-react';

import type { IntelligenceField, IntelligenceSnapshot } from './types';

type IntelligencePanelProps = {
  snapshot: IntelligenceSnapshot;
  isTyping: boolean;
  isRunning: boolean;
};

const DATA_FIELDS: { key: IntelligenceField; label: string }[] = [
  { key: 'name', label: 'Nombre' },
  { key: 'service', label: 'Servicio' },
  { key: 'preferredDay', label: 'Día' },
  { key: 'preferredTimeRange', label: 'Preferencia' },
  { key: 'selectedSlot', label: 'Horario' },
];

const PHASE_LABELS: Record<IntelligenceSnapshot['phase'], string> = {
  idle: 'Esperando',
  understanding: 'Analizando mensaje…',
  collecting_identity: 'Recopilando datos',
  collecting_service: 'Recopilando datos',
  collecting_availability: 'Recopilando datos',
  offering_slots: 'Esperando respuesta',
  confirming: 'Finalizando',
  completed: 'Completado',
};

function intentLabel(intent: IntelligenceSnapshot['intent']): string {
  switch (intent) {
    case 'book_appointment':
      return 'Reservar turno';
    case 'reschedule':
      return 'Reprogramar turno';
    case 'cancel':
      return 'Cancelar turno';
    case 'general_question':
      return 'Consulta general';
    default:
      return 'Sin detectar';
  }
}

function statusLabel(snapshot: IntelligenceSnapshot, isTyping: boolean): string {
  if (snapshot.phase === 'collecting_availability' && isTyping) return 'Consultando agenda…';
  return PHASE_LABELS[snapshot.phase];
}

export function IntelligencePanel({ snapshot, isTyping, isRunning }: IntelligencePanelProps) {
  const detectedCount = DATA_FIELDS.filter((field) => snapshot.extracted[field.key]).length;

  return (
    <section
      aria-label="Inteligencia del Recepcionista IA"
      className="min-w-0 space-y-3 rounded-2xl border border-violet-200 bg-violet-50/80 p-3"
    >
      <header className="flex items-center gap-2 px-1 py-1">
        <Sparkles
          className="h-8 w-8 shrink-0 rounded-xl bg-violet-600 p-1.5 text-white"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <h2 className="text-sm font-bold text-violet-950">Inteligencia</h2>
          <p className="text-xs text-violet-700">Comprende y conecta los datos</p>
        </div>
      </header>

      <div className="min-h-[108px] rounded-xl border border-violet-100 bg-white p-3 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-800">Estado</h3>
          <span
            aria-live="polite"
            key={`${snapshot.phase}-${isTyping}-${isRunning}`}
            className={`receptionist-intent-enter inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-semibold ${snapshot.phase === 'completed' ? 'bg-emerald-50 text-emerald-700' : isRunning ? 'bg-violet-100 text-violet-800' : 'bg-slate-100 text-slate-600'}`}
          >
            <span
              aria-hidden="true"
              className={`h-1.5 w-1.5 shrink-0 rounded-full bg-current ${isRunning ? 'receptionist-step-active' : ''}`}
            />
            {isRunning || snapshot.phase === 'idle' || snapshot.phase === 'completed'
              ? statusLabel(snapshot, isTyping)
              : 'En pausa'}
          </span>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-slate-600">
          <span className="text-xs text-slate-500">Intención detectada</span>
          <span
            key={snapshot.intent}
            className="receptionist-intent-enter min-w-0 break-words font-semibold text-violet-900"
          >
            {intentLabel(snapshot.intent)}
          </span>
        </div>
      </div>

      <div className="rounded-xl border border-violet-100 bg-white p-3 shadow-sm">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-800">Datos detectados</h3>
          <span className="shrink-0 text-xs tabular-nums text-slate-500">
            {detectedCount} de {DATA_FIELDS.length}
          </span>
        </div>

        <dl className="mt-3 space-y-2.5">
          {DATA_FIELDS.map((field) => {
            const value = snapshot.extracted[field.key];
            return (
              <div
                key={`${field.key}-${value ?? 'pending'}`}
                data-testid={`intelligence-field-${field.key}`}
                data-field-status={value ? 'completed' : 'pending'}
                className={`flex min-w-0 items-center gap-2 rounded-lg border px-2 py-2 ${value ? 'receptionist-field-enter border-violet-100 bg-violet-50' : 'border-slate-100 bg-slate-50'}`}
              >
                {value ? (
                  <Check
                    data-testid={`intelligence-field-check-${field.key}`}
                    className="receptionist-check-enter h-4 w-4 shrink-0 text-emerald-600"
                    aria-hidden="true"
                  />
                ) : (
                  <Circle className="h-4 w-4 shrink-0 text-slate-300" aria-hidden="true" />
                )}
                <dt className="w-[65px] shrink-0 text-xs text-slate-600">{field.label}</dt>
                <dd
                  key={value ?? 'waiting'}
                  className={`min-w-0 flex-1 break-words text-right text-sm ${
                    value ? 'font-semibold text-violet-900' : 'text-slate-500'
                  }`}
                >
                  {value ?? 'Pendiente'}
                </dd>
              </div>
            );
          })}
        </dl>

        <div className="mt-4">
          <div
            role="progressbar"
            aria-label="Datos detectados"
            aria-valuemin={0}
            aria-valuemax={DATA_FIELDS.length}
            aria-valuenow={detectedCount}
            className="h-2 overflow-hidden rounded-full bg-violet-100"
          >
            <div
              className="h-full rounded-full bg-violet-600 transition-[width] duration-500 motion-reduce:transition-none"
              style={{ width: `${(detectedCount / DATA_FIELDS.length) * 100}%` }}
            />
          </div>
          <p className="mt-2 text-right text-xs text-slate-500">
            {detectedCount} de {DATA_FIELDS.length} datos detectados
          </p>
        </div>
      </div>

      <div className="min-h-[290px] rounded-xl border border-violet-100 bg-white p-3 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-800">Proceso</h3>
        <ol aria-label="Proceso del recepcionista" className="mt-3 space-y-1.5">
          {snapshot.steps.map((step) => (
            <li
              key={`${step.id}-${step.status}`}
              data-testid="intelligence-step"
              data-step-status={step.status}
              aria-current={step.status === 'active' ? 'step' : undefined}
              className={`flex min-w-0 items-start gap-2 rounded-lg px-2 py-1 text-xs leading-5 ${step.status === 'active' ? 'receptionist-intent-enter bg-violet-100 ring-1 ring-inset ring-violet-200' : ''}`}
            >
              {step.status === 'completed' ? (
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden="true" />
              ) : step.status === 'active' ? (
                <span
                  className={`${isRunning ? 'receptionist-step-active ' : ''}mt-1 h-3 w-3 shrink-0 rounded-full border-2 border-violet-300 bg-violet-600`}
                  aria-hidden="true"
                />
              ) : (
                <Circle className="mt-0.5 h-4 w-4 shrink-0 text-slate-300" aria-hidden="true" />
              )}
              <span
                className={`min-w-0 break-words ${
                  step.status === 'active'
                    ? 'font-semibold text-violet-800'
                    : step.status === 'completed'
                      ? 'text-slate-700'
                      : 'text-slate-500'
                }`}
              >
                {step.label}
              </span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
