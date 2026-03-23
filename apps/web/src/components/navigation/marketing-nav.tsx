'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import Image from 'next/image';
import type { Route } from 'next';
import { Menu, X, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SiteContainer } from '@/components/layout/site-container';
import { useScrollDirection } from '@/hooks/use-scroll-direction';

const marketingLinks = [
    { href: '/pricing', label: 'Precios' },
    { href: '/services', label: 'Servicios' },
    { href: '/blog', label: 'Blog' },
    { href: '/soporte', label: 'Soporte' },
];

export function MarketingNav() {
    const { scrollDir, isAtTop } = useScrollDirection();
    const pathname = usePathname();
    const [isOpen, setIsOpen] = useState(false);

    // Bloquear scroll cuando el menú está abierto
    useEffect(() => {
        if (isOpen) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = '';
        }
        return () => {
             document.body.style.overflow = '';
        };
    }, [isOpen]);

    // Ocultar header al hacer scroll down, excepto si el menú está abierto
    const isHidden = scrollDir === 'down' && !isOpen;
    // Mostrar fondo blanco si no estamos arriba O si el menú está abierto
    const showBackground = !isAtTop || isOpen;

    return (
        <>
            <header 
                className={cn(
                    "fixed top-0 inset-x-0 z-50 w-full transition-all duration-300 ease-in-out border-b",
                    isHidden ? "-translate-y-full" : "translate-y-0",
                    showBackground
                        ? "bg-white border-zinc-100 py-3 shadow-sm" 
                        : "bg-transparent border-transparent py-5"
                )}
            >
                <SiteContainer>
                    <div className="flex items-center justify-between relative z-50">
                        {/* Logo */}
                        <Link 
                            href="/" 
                            className="flex items-center gap-2.5 group relative z-50"
                            onClick={(e) => {
                                setIsOpen(false);
                                if (pathname === '/') {
                                    e.preventDefault();
                                    window.scrollTo({ top: 0, behavior: 'smooth' });
                                }
                            }}
                            aria-label="Ir al inicio"
                        >
                            <div className="relative w-8 h-8 lg:w-9 lg:h-9 transition-transform duration-300 group-hover:scale-105">
                                <Image 
                                    src="/logo/rubroicono.png" 
                                    alt="Mirubro Logo" 
                                    fill
                                    className="object-contain"
                                    sizes="(max-width: 768px) 32px, 36px"
                                />
                            </div>
                            <span className="text-xl lg:text-2xl font-display font-semibold text-zinc-950 tracking-tight">
                                MiRubro
                            </span>
                        </Link>

                        {/* Desktop Navigation */}
                        <nav className="hidden md:flex items-center gap-8">
                            <div className="flex items-center gap-6">
                                {marketingLinks.map((link) => (
                                    <Link 
                                        key={link.href} 
                                        href={link.href as Route} 
                                        className="text-sm font-medium text-zinc-600 hover:text-brand-600 transition-colors"
                                    >
                                        {link.label}
                                    </Link>
                                ))}
                            </div>
                            
                            <Link 
                                href="/entrar" 
                                className="inline-flex items-center justify-center px-5 py-2.5 text-sm font-semibold text-white transition-all bg-zinc-900 rounded-full hover:bg-zinc-800 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-zinc-900/20"
                            >
                                Ingresar
                            </Link>
                        </nav>

                        {/* Mobile Toggle Button */}
                        <button
                            className="md:hidden p-2 -mr-2 text-zinc-800 hover:bg-zinc-100 rounded-full transition-colors"
                            onClick={() => setIsOpen(!isOpen)}
                            aria-label={isOpen ? "Cerrar menú" : "Abrir menú"}
                            aria-expanded={isOpen}
                        >
                            {isOpen ? (
                                <X className="w-6 h-6" strokeWidth={2} />
                            ) : (
                                <Menu className="w-6 h-6" strokeWidth={2} />
                            )}
                        </button>
                    </div>
                </SiteContainer>
            </header>

            {/* Mobile Menu Overlay */}
            <div
                className={cn(
                    "fixed inset-0 z-40 bg-white flex flex-col md:hidden transition-all duration-300 ease-in-out",
                    isOpen 
                        ? "opacity-100 translate-y-0 pointer-events-auto" 
                        : "opacity-0 -translate-y-4 pointer-events-none"
                )}
                style={{ paddingTop: '80px' }} // Espacio para el header fijo
            >
                <div className="flex flex-col flex-1 px-6 pb-8 overflow-y-auto">
                    <div className="flex flex-col gap-1 py-4">
                        {marketingLinks.map((link) => (
                            <Link 
                                key={link.href}
                                href={link.href as Route} 
                                onClick={() => setIsOpen(false)}
                                className="text-2xl font-medium text-zinc-800 py-4 border-b border-zinc-100 last:border-0 hover:text-brand-600 transition-colors flex items-center justify-between group"
                            >
                                {link.label}
                                <ArrowRight className="w-5 h-5 text-zinc-300 opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
                            </Link>
                        ))}
                    </div>
                    
                    <div className="mt-auto pt-6">
                        <Link 
                            href="/entrar" 
                            onClick={() => setIsOpen(false)}
                            className="flex items-center justify-center w-full h-14 bg-zinc-900 text-white rounded-xl font-bold text-lg shadow-lg hover:bg-zinc-800 active:scale-[0.98] transition-all"
                        >
                            Ingresar a mi cuenta
                        </Link>
                        
                        <div className="mt-8 text-center border-t border-zinc-50 pt-6">
                            <p className="text-sm text-zinc-400">
                                © {new Date().getFullYear()} MiRubro Digital
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </>
    );
}
