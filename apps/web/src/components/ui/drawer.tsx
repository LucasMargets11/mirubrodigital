"use client";

import { ReactNode, useEffect } from 'react';
import { createPortal } from 'react-dom';

import { cn } from '@/lib/utils';

type DrawerSide = 'left' | 'right';

type DrawerProps = {
    open: boolean;
    onClose: () => void;
    title?: string;
    children: ReactNode;
    side?: DrawerSide;
    widthClassName?: string;
};

export function Drawer({ open, onClose, title, children, side = 'right', widthClassName }: DrawerProps) {
    useEffect(() => {
        if (!open) {
            return undefined;
        }

        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                onClose();
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [open, onClose]);

    useEffect(() => {
        if (!open) {
            return undefined;
        }
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        return () => {
            document.body.style.overflow = previousOverflow;
        };
    }, [open]);

    if (!open || typeof document === 'undefined') {
        return null;
    }

    const panelClassName = cn(
        'pointer-events-auto flex h-full w-full max-w-md flex-col bg-white p-6 shadow-2xl sm:max-w-lg',
        side === 'left' ? 'border-r border-slate-100' : 'border-l border-slate-100',
        widthClassName
    );

    const drawer = (
        <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal="true">
            <button
                type="button"
                aria-label="Cerrar panel"
                onClick={onClose}
                className="absolute inset-0 bg-slate-900/60"
                tabIndex={-1}
            />
            <div
                className={cn('relative z-10 ml-auto flex h-full w-full flex-col bg-transparent', side === 'left' && 'mr-auto ml-0')}
                onClick={(event) => event.stopPropagation()}
            >
                <div className={cn(panelClassName, side === 'left' ? '' : 'ml-auto')}>
                    <div className="flex items-start justify-between gap-4">
                        {title ? (
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Panel</p>
                                <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
                            </div>
                        ) : (
                            <div className="text-sm font-semibold text-slate-900">&nbsp;</div>
                        )}
                        <button
                            type="button"
                            onClick={onClose}
                            className="rounded-full p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
                            aria-label="Cerrar"
                        >
                            ✕
                        </button>
                    </div>
                    <div className="mt-6 flex-1 overflow-y-auto pb-6">{children}</div>
                </div>
            </div>
        </div>
    );

    return createPortal(drawer, document.body);
}
