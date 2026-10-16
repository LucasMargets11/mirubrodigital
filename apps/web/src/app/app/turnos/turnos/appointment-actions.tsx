import { MoreHorizontal } from 'lucide-react';
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';

import type { Appointment } from '@/features/appointments/types';

export type AppointmentActionHandlers = {
    onEdit: (appointment: Appointment) => void;
    onStatus: (appointment: Appointment, status: 'completed' | 'no_show') => void;
    onCancel: (appointment: Appointment) => void;
};

type MenuItem = { key: string; label: string; onSelect: () => void; danger?: boolean };

/**
 * Acciones de un turno en la vista Día: "Editar" siempre visible y los
 * cambios de estado en un menú `⋯`. Mismas reglas que antes: las
 * transiciones solo existen para turnos `confirmed` (estado efectivo).
 * Quien no tiene permiso de gestión no recibe este componente.
 */
export function AppointmentActions({
    appointment,
    timeLabel,
    handlers,
}: {
    appointment: Appointment;
    /** "10:30", para que el label del menú identifique el turno. */
    timeLabel: string;
    handlers: AppointmentActionHandlers;
}) {
    const items: MenuItem[] =
        appointment.effective_status === 'confirmed'
            ? [
                  { key: 'completed', label: 'Marcar como completado', onSelect: () => handlers.onStatus(appointment, 'completed') },
                  { key: 'no_show', label: 'Marcar como no asistió', onSelect: () => handlers.onStatus(appointment, 'no_show') },
                  { key: 'cancel', label: 'Cancelar turno', onSelect: () => handlers.onCancel(appointment), danger: true },
              ]
            : [];

    return (
        <div className="flex items-center gap-1.5">
            <button
                type="button"
                onClick={() => handlers.onEdit(appointment)}
                className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-1"
            >
                Editar
            </button>
            {items.length > 0 ? (
                <ActionsMenu label={`Más acciones para el turno de ${appointment.customer_name} a las ${timeLabel}`} items={items} />
            ) : null}
        </div>
    );
}

function ActionsMenu({ label, items }: { label: string; items: MenuItem[] }) {
    const [open, setOpen] = useState(false);
    const menuId = useId();
    const containerRef = useRef<HTMLDivElement>(null);
    const triggerRef = useRef<HTMLButtonElement>(null);
    const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

    useEffect(() => {
        if (!open) return;
        itemRefs.current[0]?.focus();
        function handlePointer(event: MouseEvent) {
            if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
        }
        document.addEventListener('mousedown', handlePointer);
        return () => document.removeEventListener('mousedown', handlePointer);
    }, [open]);

    function close(restoreFocus: boolean) {
        setOpen(false);
        if (restoreFocus) triggerRef.current?.focus();
    }

    function focusItem(index: number) {
        const count = items.length;
        itemRefs.current[(index + count) % count]?.focus();
    }

    function handleMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
        const current = itemRefs.current.findIndex((el) => el === document.activeElement);
        switch (event.key) {
            case 'ArrowDown':
                event.preventDefault();
                focusItem(current + 1);
                break;
            case 'ArrowUp':
                event.preventDefault();
                focusItem(current - 1);
                break;
            case 'Home':
                event.preventDefault();
                focusItem(0);
                break;
            case 'End':
                event.preventDefault();
                focusItem(items.length - 1);
                break;
            case 'Escape':
                event.preventDefault();
                close(true);
                break;
            case 'Tab':
                close(false);
                break;
        }
    }

    return (
        <div ref={containerRef} className="relative">
            <button
                ref={triggerRef}
                type="button"
                aria-label={label}
                aria-haspopup="menu"
                aria-expanded={open}
                aria-controls={open ? menuId : undefined}
                onClick={() => setOpen((prev) => !prev)}
                onKeyDown={(event) => {
                    if (event.key === 'ArrowDown' && !open) {
                        event.preventDefault();
                        setOpen(true);
                    }
                }}
                className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 hover:border-slate-900 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-1"
            >
                <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
            </button>
            {open ? (
                <div
                    id={menuId}
                    role="menu"
                    aria-label={label}
                    onKeyDown={handleMenuKeyDown}
                    className="absolute right-0 z-20 mt-1 w-52 rounded-xl border border-slate-200 bg-white py-1 shadow-lg"
                >
                    {items.map((item, index) => (
                        <button
                            key={item.key}
                            ref={(el) => {
                                itemRefs.current[index] = el;
                            }}
                            type="button"
                            role="menuitem"
                            tabIndex={-1}
                            onClick={() => {
                                close(true);
                                item.onSelect();
                            }}
                            className={`block w-full px-3 py-2 text-left text-sm focus:outline-none ${
                                item.danger
                                    ? 'text-rose-600 hover:bg-rose-50 focus:bg-rose-50'
                                    : 'text-slate-700 hover:bg-slate-50 focus:bg-slate-50'
                            }`}
                        >
                            {item.label}
                        </button>
                    ))}
                </div>
            ) : null}
        </div>
    );
}
