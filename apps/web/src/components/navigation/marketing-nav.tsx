'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { cn } from '@/lib/utils';

const marketingLinks = [
    { href: '/', label: 'Inicio' },
    { href: '/pricing', label: 'Precios' },
    { href: '/services', label: 'Servicios' },
    { href: '/entrar', label: 'Entrar' },
];

export function MarketingNav() {
    const [scrolled, setScrolled] = useState(false);

    useEffect(() => {
        const handleScroll = () => {
            setScrolled(window.scrollY > 8);
        };

        window.addEventListener('scroll', handleScroll, { passive: true });
        return () => window.removeEventListener('scroll', handleScroll);
    }, []);

    return (
        <header className={cn(
            "sticky top-0 z-50 w-full transition-all duration-200",
            scrolled 
                ? "bg-white/80 supports-[backdrop-filter]:bg-white/60 supports-[backdrop-filter]:backdrop-blur-md shadow-sm border-b border-black/5"
                : "bg-transparent"
        )}>
            <div className="mx-auto max-w-7xl px-6 lg:px-10">
                <div className="flex items-center justify-between h-16">
                    <Link href="/" className="flex items-center gap-2 text-xl font-display font-semibold text-brand-600">
                        <Image src="/logo/rubroicono.png" alt="Mirubro Logo" width={32} height={32} />
                        Mirubro
                    </Link>
                    <nav className="flex gap-6 text-sm font-medium text-slate-700">
                        {marketingLinks.map((link) => (
                            <Link key={link.href} href={link.href} className="hover:text-brand-600 transition-colors">
                                {link.label}
                            </Link>
                        ))}
                    </nav>
                </div>
            </div>
        </header>
    );
}
