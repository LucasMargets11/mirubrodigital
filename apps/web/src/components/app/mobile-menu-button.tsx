"use client";

import { Menu } from 'lucide-react';
import { useMobileMenu } from './mobile-menu-context';

export function MobileMenuButton() {
    const { open } = useMobileMenu();

    return (
        <button
            type="button"
            onClick={open}
            className="md:hidden rounded-md p-2 text-slate-600 hover:bg-slate-100 transition-colors"
            aria-label="Abrir menú"
        >
            <Menu className="h-6 w-6" />
        </button>
    );
}
