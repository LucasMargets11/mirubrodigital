import Link from 'next/link';

const marketingLinks = [
    { href: '/', label: 'Inicio' },
    { href: '/pricing', label: 'Precios' },
    { href: '/features', label: 'Funciones' },
    { href: '/entrar', label: 'Entrar' },
];

export function MarketingNav() {
    return (
        <header className="flex items-center justify-between py-6">
            <Link href="/" className="text-xl font-display font-semibold text-brand-600">
                Mirubro
            </Link>
            <nav className="flex gap-6 text-sm font-medium text-slate-700">
                {marketingLinks.map((link) => (
                    <Link key={link.href} href={link.href} className="hover:text-brand-600">
                        {link.label}
                    </Link>
                ))}
            </nav>
        </header>
    );
}
