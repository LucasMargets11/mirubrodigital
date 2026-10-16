"use client";

import { ReactNode, useEffect } from 'react';
import { createPortal } from 'react-dom';

type ModalProps = {
    open: boolean;
    title: string;
    onClose: () => void;
    children: ReactNode;
    /**
     * Acciones fijas al pie. Con `footer` el modal usa el layout acotado al
     * viewport: header y footer fijos, y SOLO el cuerpo scrollea (nunca queda
     * fuera de pantalla en alturas chicas ni detrás de barras del sistema).
     */
    footer?: ReactNode;
    /** Rótulo chico sobre el título; `null` lo oculta. Default "Formulario" (comportamiento histórico). */
    eyebrow?: string | null;
};

export function Modal({ open, title, onClose, children, footer, eyebrow = 'Formulario' }: ModalProps) {
    useEffect(() => {
        if (!open) {
            document.body.style.overflow = '';
            document.body.style.paddingRight = '';
            return () => {
                document.body.style.overflow = '';
                document.body.style.paddingRight = '';
            };
        }

        const previousOverflow = document.body.style.overflow;
        const previousPaddingRight = document.body.style.paddingRight;
        const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;

        document.body.style.overflow = 'hidden';
        if (scrollbarWidth > 0) {
            document.body.style.paddingRight = `${scrollbarWidth}px`;
        }

        return () => {
            document.body.style.overflow = previousOverflow;
            document.body.style.paddingRight = previousPaddingRight;
        };
    }, [open]);

    if (!open || typeof document === 'undefined') {
        return null;
    }

    const header = (
        <div className="flex items-start justify-between">
            <div>
                {eyebrow ? <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{eyebrow}</p> : null}
                <h3 className="text-xl font-semibold text-slate-900">{title}</h3>
            </div>
            <button
                type="button"
                onClick={onClose}
                className="rounded-full p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
                aria-label="Cerrar"
            >
                ✕
            </button>
        </div>
    );

    const modal = (
        <div className="fixed inset-0 z-50 overflow-y-auto" role="dialog" aria-modal="true" aria-label={title}>
            <button
                type="button"
                aria-label="Cerrar"
                onClick={onClose}
                className="fixed inset-0 h-full w-full bg-slate-900/60"
            />
            {footer !== undefined ? (
                <div
                    className="relative z-10 flex min-h-full items-center justify-center p-2 sm:p-4"
                    onClick={(event) => event.stopPropagation()}
                >
                    <div
                        data-testid="modal-panel"
                        className="flex max-h-[calc(100dvh-1rem)] w-full max-w-xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl sm:max-h-[calc(100dvh-2rem)]"
                    >
                        <div data-testid="modal-header" className="shrink-0 border-b border-slate-100 px-4 pb-3 pt-4 sm:px-6 sm:pt-6">
                            {header}
                        </div>
                        <div
                            data-testid="modal-body"
                            className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-4 sm:px-6"
                        >
                            {children}
                        </div>
                        <div data-testid="modal-footer" className="shrink-0 border-t border-slate-100 px-4 py-3 sm:px-6 sm:py-4">
                            {footer}
                        </div>
                    </div>
                </div>
            ) : (
                <div className="relative z-10 flex min-h-full items-center justify-center p-4" onClick={(event) => event.stopPropagation()}>
                    <div className="w-full max-w-xl rounded-2xl bg-white p-6 shadow-2xl">
                        {header}
                        <div className="mt-6 space-y-4">{children}</div>
                    </div>
                </div>
            )}
        </div>
    );

    return createPortal(modal, document.body);
}
