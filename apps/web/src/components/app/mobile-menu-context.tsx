"use client";

import { createContext, useContext, ReactNode, useState } from 'react';

type MobileMenuContextValue = {
    isOpen: boolean;
    open: () => void;
    close: () => void;
    toggle: () => void;
};

const MobileMenuContext = createContext<MobileMenuContextValue | null>(null);

export function MobileMenuProvider({ children }: { children: ReactNode }) {
    const [isOpen, setIsOpen] = useState(false);

    return (
        <MobileMenuContext.Provider
            value={{
                isOpen,
                open: () => setIsOpen(true),
                close: () => setIsOpen(false),
                toggle: () => setIsOpen((prev) => !prev),
            }}
        >
            {children}
        </MobileMenuContext.Provider>
    );
}

export function useMobileMenu() {
    const context = useContext(MobileMenuContext);
    if (!context) {
        throw new Error('useMobileMenu must be used within MobileMenuProvider');
    }
    return context;
}
