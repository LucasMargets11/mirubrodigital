'use client';

import { createContext, useContext, useMemo, useState } from 'react';
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react';

import { cn } from '@/lib/utils';

type TabsContextValue = {
    value: string;
    setValue: (value: string) => void;
};

const TabsContext = createContext<TabsContextValue | null>(null);

export type TabsProps = {
    defaultValue: string;
    value?: string;
    onValueChange?: (value: string) => void;
    children: ReactNode;
    className?: string;
};

export function Tabs({ defaultValue, value, onValueChange, children, className }: TabsProps) {
    const [internalValue, setInternalValue] = useState(defaultValue);
    const activeValue = value ?? internalValue;

    const contextValue = useMemo<TabsContextValue>(
        () => ({
            value: activeValue,
            setValue: (nextValue: string) => {
                if (!value) {
                    setInternalValue(nextValue);
                }
                onValueChange?.(nextValue);
            }
        }),
        [activeValue, onValueChange, value]
    );

    return (
        <TabsContext.Provider value={contextValue}>
            <div className={cn('w-full', className)}>{children}</div>
        </TabsContext.Provider>
    );
}

function useTabsContext() {
    const context = useContext(TabsContext);
    if (!context) {
        throw new Error('Tabs components must be used within <Tabs>.');
    }
    return context;
}

export type TabsListProps = HTMLAttributes<HTMLDivElement>;

export function TabsList({ className, ...props }: TabsListProps) {
    return (
        <div
            role="tablist"
            className={cn('inline-flex items-center justify-center gap-1 rounded-full bg-slate-100 p-1 text-sm font-medium', className)}
            {...props}
        />
    );
}

export type TabsTriggerProps = ButtonHTMLAttributes<HTMLButtonElement> & {
    value: string;
};

export function TabsTrigger({ value, className, children, ...props }: TabsTriggerProps) {
    const { value: activeValue, setValue } = useTabsContext();
    const isActive = activeValue === value;

    return (
        <button
            type="button"
            role="tab"
            aria-selected={isActive}
            data-state={isActive ? 'active' : 'inactive'}
            onClick={() => setValue(value)}
            className={cn(
                'inline-flex min-w-[120px] items-center justify-center whitespace-nowrap rounded-full px-4 py-2 text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2',
                isActive ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500 hover:text-slate-700',
                className
            )}
            {...props}
        >
            {children}
        </button>
    );
}

export type TabsContentProps = HTMLAttributes<HTMLDivElement> & {
    value: string;
};

export function TabsContent({ value, className, children, ...props }: TabsContentProps) {
    const { value: activeValue } = useTabsContext();
    const isActive = activeValue === value;

    return (
        <div
            role="tabpanel"
            hidden={!isActive}
            data-state={isActive ? 'active' : 'inactive'}
            className={cn('w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2', className)}
            {...props}
        >
            {isActive ? children : null}
        </div>
    );
}
