"use client";

import { ReactNode, useEffect } from 'react';
import { createPortal } from 'react-dom';

type ModalProps = {
    open: boolean;
    title: string;
    onClose: () => void;
    children: ReactNode;
};

export function Modal({ open, title, onClose, children }: ModalProps) {
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

    const modal = (
        <div className="fixed inset-0 z-50" role="dialog" aria-modal="true">
            <button
                type="button"
                aria-label="Cerrar"
                onClick={onClose}
                className="absolute inset-0 h-full w-full bg-slate-900/60"
            />
            <div className="relative z-10 flex min-h-full items-center justify-center p-4" onClick={(event) => event.stopPropagation()}>
                <div className="w-full max-w-xl rounded-2xl bg-white p-6 shadow-2xl">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Formulario</p>
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
                    <div className="mt-6 space-y-4">{children}</div>
                </div>
            </div>
        </div>
    );

    return createPortal(modal, document.body);
}
