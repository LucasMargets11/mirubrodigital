'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import Image from 'next/image';
import type { Route } from 'next';
import { Menu, X, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useScrollDirection } from '@/hooks/use-scroll-direction';

const marketingLinks = [
    { href: '/gestion', label: 'Gestión Comercial' },
    { href: '/carta', label: 'Carta Online' },
    { href: '/resenas', label: 'QR de Reseñas' },
    { href: '/pricing', label: 'Precios' },
    { href: '/blog', label: 'Blog' },
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
                        ? "bg-white/95 backdrop-blur-xl border-zinc-200/60 py-3.5 lg:py-4 shadow-[0_1px_3px_0_rgb(0,0,0,0.04)]" 
                        : "bg-transparent border-transparent py-5 lg:py-6"
                )}
            >
                <div className="mx-auto w-full max-w-[1400px] px-6 lg:px-12">
                    <div className="flex items-center justify-between relative z-50">
                        {/* Logo */}
                        <Link 
                            href="/" 
                            className="flex items-center gap-3 group relative z-50"
                            onClick={(e) => {
                                setIsOpen(false);
                                if (pathname === '/') {
                                    e.preventDefault();
                                    window.scrollTo({ top: 0, behavior: 'smooth' });
                                }
                            }}
                            aria-label="Ir al inicio"
                        >
                            <div className="relative w-9 h-9 lg:w-10 lg:h-10 transition-transform duration-300 group-hover:scale-105">
                                <Image 
                                    src="/logo/rubroicono.png" 
                                    alt="Mirubro Logo" 
                                    fill
                                    className="object-contain"
                                    sizes="(max-width: 768px) 36px, 40px"
                                />
                            </div>
                            <span className="text-[1.35rem] lg:text-[1.6rem] font-display font-bold text-zinc-950 tracking-tight">
                                MiRubro
                            </span>
                        </Link>

                        {/* Desktop Navigation */}
                        <nav className="hidden lg:flex items-center gap-10">
                            <div className="flex items-center gap-7">
                                {marketingLinks.map((link) => (
                                    <Link 
                                        key={link.href} 
                                        href={link.href as Route} 
                                        className="text-[0.8125rem] font-semibold text-zinc-600 hover:text-zinc-900 transition-colors whitespace-nowrap"
                                    >
                                        {link.label}
                                    </Link>
                                ))}
                            </div>

                            <div className="flex items-center gap-3">
                                <Link 
                                    href="/entrar" 
                                    className="inline-flex items-center justify-center px-6 py-2.5 text-sm font-semibold text-zinc-700 border border-zinc-300 rounded-full hover:bg-zinc-50 hover:border-zinc-400 transition-all focus:outline-none focus:ring-2 focus:ring-zinc-900/20 whitespace-nowrap"
                                >
                                    Ingresar
                                </Link>
                                <Link 
                                    href="/entrar" 
                                    className="inline-flex items-center justify-center px-6 py-2.5 text-sm font-bold text-white transition-all bg-zinc-900 rounded-full hover:bg-zinc-800 shadow-sm hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-zinc-900/20 whitespace-nowrap"
                                >
                                    Empezar
                                </Link>
                            </div>
                        </nav>

                        {/* Mobile Toggle Button */}
                        <button
                            className="lg:hidden p-2 -mr-2 text-zinc-800 hover:bg-zinc-100 rounded-full transition-colors"
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
                </div>
            </header>

            {/* Mobile Menu Overlay */}
            <div
                className={cn(
                    "fixed inset-0 z-40 bg-white flex flex-col lg:hidden transition-all duration-300 ease-in-out",
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
                    
                    <div className="mt-auto pt-6 space-y-3">
                        <Link 
                            href="/entrar" 
                            onClick={() => setIsOpen(false)}
                            className="flex items-center justify-center w-full h-14 bg-zinc-900 text-white rounded-xl font-bold text-lg shadow-lg hover:bg-zinc-800 active:scale-[0.98] transition-all"
                        >
                            Empezar
                        </Link>
                        <Link 
                            href="/entrar" 
                            onClick={() => setIsOpen(false)}
                            className="flex items-center justify-center w-full h-14 border border-zinc-200 text-zinc-700 rounded-xl font-semibold text-lg hover:bg-zinc-50 active:scale-[0.98] transition-all"
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
