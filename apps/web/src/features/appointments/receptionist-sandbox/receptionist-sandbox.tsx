'use client';

import { Pause, Play, RotateCcw } from 'lucide-react';

import { Button } from '@/components/ui/button';

import { ConversationPanel } from './conversation-panel';
import { IntelligencePanel } from './intelligence-panel';
import { MiRubroPanel } from './mirubro-panel';
import { SandboxLayout } from './sandbox-layout';
import { RESERVAR_TURNO_SCENARIO } from './simulation-data';
import { useReceptionistSimulation } from './simulation-engine';
import type { SimulationStatus } from './types';

const PRIMARY_LABEL: Record<SimulationStatus, string> = {
  idle: 'Iniciar demo',
  running: 'Pausar',
  paused: 'Reanudar',
  completed: 'Repetir demo',
};

const STATUS_ANNOUNCEMENT: Record<SimulationStatus, string> = {
  idle: 'Simulación en espera.',
  running: 'Simulación en curso.',
  paused: 'Simulación en pausa.',
  completed: 'Simulación completada.',
};

const STATUS_LABEL: Record<SimulationStatus, string> = {
  idle: 'Lista para iniciar',
  running: 'En vivo',
  paused: 'En pausa',
  completed: 'Completada',
};

export function ReceptionistSandbox() {
  const simulation = useReceptionistSimulation(RESERVAR_TURNO_SCENARIO);
  const { status, messages, isTyping, intelligence, mirubro, start, pause, resume, restart } =
    simulation;

  const handlePrimaryAction = () => {
    if (status === 'running') pause();
    else if (status === 'paused') resume();
    else start();
  };

  const PrimaryIcon = status === 'running' ? Pause : Play;

  return (
    <>
      <SandboxLayout
        toolbar={
          <>
            <div className="mr-auto flex min-h-14 w-full min-w-0 flex-wrap items-center gap-2 sm:min-h-0 sm:w-auto">
              <span className="text-sm font-semibold text-slate-800">
                {RESERVAR_TURNO_SCENARIO.label}
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
                <span
                  aria-hidden="true"
                  className={`h-1.5 w-1.5 rounded-full ${status === 'running' ? 'bg-emerald-500' : status === 'paused' ? 'bg-amber-500' : 'bg-slate-400'}`}
                />
                {STATUS_LABEL[status]}
              </span>
            </div>
            <Button
              type="button"
              size="sm"
              onClick={handlePrimaryAction}
              className="gap-1 rounded-full px-2 text-xs sm:gap-1.5 sm:px-3 sm:text-sm"
            >
              <PrimaryIcon className="h-3.5 w-3.5" aria-hidden="true" />
              {PRIMARY_LABEL[status]}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={restart}
              disabled={status === 'idle'}
              className="gap-1 rounded-full px-2 text-xs sm:gap-1.5 sm:px-3 sm:text-sm"
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
              Reiniciar
            </Button>
          </>
        }
        intelligence={
          <IntelligencePanel
            snapshot={intelligence}
            isTyping={isTyping}
            isRunning={status === 'running'}
          />
        }
        conversation={<ConversationPanel messages={messages} isTyping={isTyping} status={status} />}
        mirubro={<MiRubroPanel snapshot={mirubro} />}
      />
      <p role="status" aria-live="polite" className="sr-only">
        {STATUS_ANNOUNCEMENT[status]}
      </p>
    </>
  );
}
