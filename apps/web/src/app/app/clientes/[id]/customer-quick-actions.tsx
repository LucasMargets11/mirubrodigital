"use client";

import { useEffect, useId, useRef, useState } from 'react';

import { Modal } from '@/components/ui/modal';
import { mailtoHref, telHref, whatsappHref } from '@/features/customers/contact-links';

type CustomerQuickActionsProps = {
    phone: string | null;
    email: string | null;
    /** Sin callback la acción no se muestra (permiso/módulo ausente). */
    onNewAppointment?: () => void;
    onEdit?: () => void;
    onAddNote?: () => void;
    /** CUSTOMER 07A: abre el formulario de la sección Recordatorios (`manage_customer_reminders`). */
    onNewReminder?: () => void;
    /**
     * CUSTOMER 07D.1: el cliente pidió no ser contactado. Las acciones
     * manuales NO se ocultan: antes de abrir WhatsApp/Llamar/Email se muestra
     * una advertencia y la persona decide.
     */
    doNotContact?: boolean;
};

type ContactLink = { key: string; label: string; href: string; external?: boolean };

type SecondaryAction =
    | { key: string; label: string; kind: 'button'; onClick: () => void }
    | { key: string; label: string; kind: 'link'; href: string; title: string; external?: boolean };

const ITEM_CLASS =
    'flex min-h-11 w-full items-center rounded-xl px-4 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50 hover:text-slate-900 ' +
    'md:min-h-0 md:w-auto md:rounded-full md:border md:border-slate-200 md:px-4 md:py-2 md:hover:border-slate-900 md:hover:bg-transparent';

/**
 * Acciones rápidas de la ficha (CUSTOMER 06). Solo se renderiza lo que el
 * rol puede hacer y lo que los datos permiten (sin teléfono no hay
 * WhatsApp/Llamar; sin email no hay Email). Los contactos son links
 * manuales: nada se envía ni se guarda.
 *
 * Desktop: toolbar en línea. Mobile: "Nuevo turno" visible y el resto en un
 * desplegable "Más" con targets de 44px (mismo DOM, solo cambia el layout).
 */
export function CustomerQuickActions({
    phone,
    email,
    onNewAppointment,
    onEdit,
    onAddNote,
    onNewReminder,
    doNotContact = false,
}: CustomerQuickActionsProps) {
    const [menuOpen, setMenuOpen] = useState(false);
    const [pendingContact, setPendingContact] = useState<ContactLink | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const listId = useId();

    useEffect(() => {
        if (!menuOpen) return;
        function onPointerDown(event: MouseEvent) {
            if (containerRef.current && !containerRef.current.contains(event.target as Node)) setMenuOpen(false);
        }
        function onKeyDown(event: KeyboardEvent) {
            if (event.key === 'Escape') setMenuOpen(false);
        }
        document.addEventListener('mousedown', onPointerDown);
        document.addEventListener('keydown', onKeyDown);
        return () => {
            document.removeEventListener('mousedown', onPointerDown);
            document.removeEventListener('keydown', onKeyDown);
        };
    }, [menuOpen]);

    const whatsapp = whatsappHref(phone);
    const tel = telHref(phone);
    const mailto = mailtoHref(email);

    const secondary: SecondaryAction[] = [];
    if (onEdit) secondary.push({ key: 'edit', label: 'Editar cliente', kind: 'button', onClick: onEdit });
    if (onAddNote) secondary.push({ key: 'note', label: 'Agregar nota', kind: 'button', onClick: onAddNote });
    if (onNewReminder) secondary.push({ key: 'reminder', label: 'Nuevo recordatorio', kind: 'button', onClick: onNewReminder });
    if (whatsapp) secondary.push({ key: 'whatsapp', label: 'WhatsApp', kind: 'link', href: whatsapp, title: `WhatsApp a ${phone}`, external: true });
    if (tel) secondary.push({ key: 'tel', label: 'Llamar', kind: 'link', href: tel, title: `Llamar a ${phone}` });
    if (mailto) secondary.push({ key: 'email', label: 'Email', kind: 'link', href: mailto, title: `Email a ${email}` });

    if (!onNewAppointment && secondary.length === 0) return null;

    return (
        <div ref={containerRef} role="toolbar" aria-label="Acciones del cliente" className="relative flex flex-wrap items-center gap-2 lg:max-w-[60%] lg:justify-end">
            {onNewAppointment ? (
                <button
                    type="button"
                    onClick={onNewAppointment}
                    className="min-h-11 rounded-full bg-slate-900 px-5 text-sm font-semibold text-white hover:bg-slate-800 md:min-h-0 md:py-2"
                >
                    Nuevo turno
                </button>
            ) : null}

            {secondary.length > 0 ? (
                <>
                    <button
                        type="button"
                        aria-expanded={menuOpen}
                        aria-controls={listId}
                        onClick={() => setMenuOpen((open) => !open)}
                        className="min-h-11 rounded-full border border-slate-200 px-4 text-sm font-semibold text-slate-700 hover:border-slate-900 md:hidden"
                    >
                        {onNewAppointment ? 'Más' : 'Acciones'} <span aria-hidden="true">▾</span>
                    </button>
                    <ul
                        id={listId}
                        data-testid="customer-secondary-actions"
                        className={`${menuOpen ? 'flex' : 'hidden'} absolute left-0 top-full z-20 mt-2 w-56 flex-col gap-1 rounded-2xl border border-slate-200 bg-white p-2 shadow-lg md:contents`}
                    >
                        {secondary.map((action) => (
                            <li key={action.key}>
                                {action.kind === 'button' ? (
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setMenuOpen(false);
                                            action.onClick();
                                        }}
                                        className={ITEM_CLASS}
                                    >
                                        {action.label}
                                    </button>
                                ) : (
                                    <a
                                        href={action.href}
                                        title={action.title}
                                        onClick={(event) => {
                                            setMenuOpen(false);
                                            if (doNotContact) {
                                                event.preventDefault();
                                                setPendingContact({ key: action.key, label: action.label, href: action.href, external: action.external });
                                            }
                                        }}
                                        {...(action.external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
                                        className={ITEM_CLASS}
                                    >
                                        {action.label}
                                    </a>
                                )}
                            </li>
                        ))}
                    </ul>
                </>
            ) : null}

            {pendingContact ? <DoNotContactWarningModal contact={pendingContact} onClose={() => setPendingContact(null)} /> : null}
        </div>
    );
}

function DoNotContactWarningModal({ contact, onClose }: { contact: ContactLink; onClose: () => void }) {
    const footer = (
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end sm:gap-3">
            <button
                type="button"
                onClick={onClose}
                className="rounded-full border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900 sm:py-2"
            >
                Cancelar
            </button>
            <a
                href={contact.href}
                onClick={onClose}
                {...(contact.external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
                className="rounded-full border border-rose-600 bg-rose-600 px-5 py-2.5 text-center text-sm font-semibold text-white sm:py-2"
            >
                Contactar igual ({contact.label})
            </a>
        </div>
    );
    return (
        <Modal open eyebrow={null} title="Este cliente pidió no ser contactado" onClose={onClose} footer={footer}>
            <p className="text-sm text-slate-600">
                En sus preferencias de contacto figura “No contactar”. Contactalo solo si es imprescindible (por ejemplo, un cambio en un
                turno que ya reservó).
            </p>
        </Modal>
    );
}
