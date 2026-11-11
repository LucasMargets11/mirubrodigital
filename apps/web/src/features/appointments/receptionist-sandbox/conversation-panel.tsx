// TURNOS RECEPCIONISTA 01: chat central del sandbox (inspirado en apps de
// mensajería modernas; sin assets ni identidad de WhatsApp).

'use client';

import { useEffect, useRef } from 'react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

import { DEMO_CONTACT_PHONE } from './simulation-data';
import type { ChatMessage, SimulationStatus } from './types';

type ConversationPanelProps = {
  messages: ChatMessage[];
  isTyping: boolean;
  status: SimulationStatus;
};

const CONTACT_NAME = 'Lucía Fernández';

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function initialsOf(name: string): string {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}

export function ConversationPanel({ messages, isTyping, status }: ConversationPanelProps) {
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const log = logRef.current;
    log?.scrollTo({
      top: log.scrollHeight,
      behavior: prefersReducedMotion() ? 'auto' : 'smooth',
    });
  }, [messages.length, isTyping]);

  const isAutomaticFlowActive = status === 'running';
  const composerPlaceholder = isAutomaticFlowActive
    ? 'La simulación automática está en curso'
    : 'Modo interactivo próximamente';

  return (
    <section
      aria-label="Conversación con el Recepcionista IA"
      className="flex h-full min-w-0 flex-col overflow-hidden rounded-2xl border border-teal-200 bg-[#f0f7f5] shadow-lg shadow-teal-950/5"
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-teal-200 bg-white px-3 py-4 sm:gap-3 sm:px-4">
        <div
          aria-hidden="true"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-teal-700 text-sm font-semibold text-white"
        >
          {initialsOf(CONTACT_NAME)}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold uppercase tracking-widest text-teal-700">Chat</p>
          <p className="break-words text-sm font-semibold text-slate-900">{CONTACT_NAME}</p>
          <p className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
            <span className="relative flex h-2 w-2">
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            <span>{isTyping && status === 'running' ? 'Escribiendo…' : 'En línea'}</span>
            <span className="break-all">{DEMO_CONTACT_PHONE}</span>
          </p>
        </div>
        <Badge variant="outline" className="shrink-0 border-teal-200 bg-teal-50 text-teal-800">
          Simulación
        </Badge>
      </header>

      <div
        ref={logRef}
        role="log"
        aria-label="Mensajes de la conversación"
        aria-live="polite"
        className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-3 py-5 sm:px-5"
      >
        {messages.length === 0 && !isTyping ? (
          <p className="pt-8 text-center text-sm text-slate-400">
            Iniciá la demo para ver la conversación.
          </p>
        ) : null}

        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}

        {isTyping ? <TypingBubble paused={status === 'paused'} /> : null}

        {status === 'completed' ? (
          <div className="flex justify-center pt-2">
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-800">
              Simulación completada
            </span>
          </div>
        ) : null}
      </div>

      <form
        className="flex flex-wrap items-center gap-2 border-t border-teal-200 bg-white/90 px-3 py-3"
        onSubmit={(event) => event.preventDefault()}
        aria-label="Modo interactivo próximamente"
      >
        <input
          type="text"
          disabled
          placeholder={composerPlaceholder}
          aria-label="Escribir un mensaje"
          className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-slate-100 px-3 py-2.5 text-xs text-slate-700 placeholder:text-slate-500 disabled:cursor-not-allowed"
        />
        <button
          type="submit"
          disabled
          aria-label="Enviar mensaje"
          title="Modo interactivo próximamente"
          className="shrink-0 rounded-xl bg-teal-700 px-3 py-2.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          Enviar
        </button>
        <p className="w-full text-center text-[10px] text-slate-500">
          Simulación automática · No se envían mensajes
        </p>
      </form>
    </section>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const fromCustomer = message.role === 'customer';

  return (
    <div
      className={cn(
        'receptionist-message-enter flex',
        fromCustomer ? 'justify-start' : 'justify-end',
      )}
    >
      <div
        data-testid="receptionist-message-bubble"
        data-role={message.role}
        className={cn(
          'max-w-[90%] rounded-2xl border px-3.5 py-2.5 text-sm leading-relaxed shadow-sm sm:max-w-[85%]',
          fromCustomer
            ? 'rounded-tl-sm border-white bg-white text-slate-800'
            : 'rounded-tr-sm border-teal-700 bg-teal-700 text-white',
        )}
      >
        <p
          className={`mb-1 text-[10px] font-semibold ${fromCustomer ? 'text-slate-500' : 'text-teal-100'}`}
        >
          {fromCustomer ? 'Lucía · Cliente' : 'Recepcionista IA'}
        </p>
        <p className="whitespace-pre-wrap break-words">{message.text}</p>
      </div>
    </div>
  );
}

function TypingBubble({ paused }: { paused: boolean }) {
  return (
    <div
      className="receptionist-message-enter flex justify-end"
      data-testid="receptionist-typing-indicator"
    >
      <div
        role="status"
        aria-label={paused ? 'Escritura en pausa' : 'El recepcionista está escribiendo'}
        className="flex flex-wrap items-center gap-1.5 rounded-2xl rounded-tr-sm bg-teal-700 px-4 py-3 text-white shadow-sm"
      >
        <span className="mr-1 text-xs">{paused ? 'En pausa' : 'Escribiendo'}</span>
        {[0, 1, 2].map((dot) => (
          <span
            key={dot}
            className={`${paused ? '' : 'receptionist-typing-dot '}h-1.5 w-1.5 rounded-full bg-white`}
            style={{ animationDelay: `${dot * 160}ms` }}
          />
        ))}
      </div>
    </div>
  );
}
