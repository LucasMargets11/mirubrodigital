"use client";

import * as React from 'react';
import { X } from 'lucide-react';

import { cn } from '@/lib/utils';

interface SheetContextValue {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

const SheetContext = React.createContext<SheetContextValue | undefined>(undefined);

function useSheet() {
    const context = React.useContext(SheetContext);
    if (!context) {
        throw new Error('Sheet components must be used within a Sheet');
    }
    return context;
}

interface SheetProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    children: React.ReactNode;
}

export function Sheet({ open, onOpenChange, children }: SheetProps) {
    // Lock body scroll when sheet is open
    React.useEffect(() => {
        if (open) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = '';
        }
        return () => {
            document.body.style.overflow = '';
        };
    }, [open]);

    // Close on Escape key
    React.useEffect(() => {
        const handleEscape = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && open) {
                onOpenChange(false);
            }
        };
        document.addEventListener('keydown', handleEscape);
        return () => document.removeEventListener('keydown', handleEscape);
    }, [open, onOpenChange]);

    return (
        <SheetContext.Provider value={{ open, onOpenChange }}>
            {children}
        </SheetContext.Provider>
    );
}

interface SheetTriggerProps {
    children: React.ReactNode;
    asChild?: boolean;
}

export function SheetTrigger({ children, asChild }: SheetTriggerProps) {
    const { onOpenChange } = useSheet();

    if (asChild && React.isValidElement(children)) {
        return React.cloneElement(children, {
            onClick: (e: React.MouseEvent) => {
                onOpenChange(true);
                children.props.onClick?.(e);
            },
        } as React.HTMLAttributes<HTMLElement>);
    }

    return (
        <button type="button" onClick={() => onOpenChange(true)}>
            {children}
        </button>
    );
}

interface SheetContentProps {
    children: React.ReactNode;
    side?: 'left' | 'right';
    className?: string;
}

export function SheetContent({ children, side = 'left', className }: SheetContentProps) {
    const { open, onOpenChange } = useSheet();

    if (!open) return null;

    const slideDirection = side === 'left' ? '-translate-x-full' : 'translate-x-full';
    const slideActive = side === 'left' ? 'translate-x-0' : 'translate-x-0';

    return (
        <>
            {/* Overlay */}
            <div
                className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm transition-opacity"
                onClick={() => onOpenChange(false)}
                aria-hidden="true"
            />

            {/* Sheet Panel */}
            <div
                className={cn(
                    'fixed inset-y-0 z-50 flex flex-col bg-white shadow-xl transition-transform duration-300',
                    side === 'left' ? 'left-0' : 'right-0',
                    open ? slideActive : slideDirection,
                    className
                )}
            >
                {children}
            </div>
        </>
    );
}

interface SheetCloseProps {
    children: React.ReactNode;
    asChild?: boolean;
}

export function SheetClose({ children, asChild }: SheetCloseProps) {
    const { onOpenChange } = useSheet();

    if (asChild && React.isValidElement(children)) {
        return React.cloneElement(children, {
            onClick: (e: React.MouseEvent) => {
                onOpenChange(false);
                children.props.onClick?.(e);
            },
        } as React.HTMLAttributes<HTMLElement>);
    }

    return (
        <button type="button" onClick={() => onOpenChange(false)}>
            {children}
        </button>
    );
}

interface SheetHeaderProps {
    children: React.ReactNode;
    className?: string;
}

export function SheetHeader({ children, className }: SheetHeaderProps) {
    return (
        <div className={cn('flex items-center justify-between border-b border-slate-200 px-4 py-4', className)}>
            {children}
        </div>
    );
}

interface SheetTitleProps {
    children: React.ReactNode;
    className?: string;
}

export function SheetTitle({ children, className }: SheetTitleProps) {
    return <h2 className={cn('text-lg font-semibold text-slate-900', className)}>{children}</h2>;
}

export function SheetCloseButton() {
    const { onOpenChange } = useSheet();
    return (
        <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="rounded-md p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-900"
            aria-label="Cerrar menú"
        >
            <X className="h-5 w-5" />
        </button>
    );
}
