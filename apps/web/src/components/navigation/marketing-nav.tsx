import Link from 'next/link';
import Image from 'next/image';
import { MarketingContainer } from '@/components/ui/marketing-container';

const marketingLinks = [
    { href: '/', label: 'Inicio' },
    { href: '/pricing', label: 'Precios' },
    { href: '/services', label: 'Servicios' },
    { href: '/entrar', label: 'Entrar' },
];

export function MarketingNav() {
    return (
        <header className="w-full bg-white py-6">
            <MarketingContainer>
                <div className="flex items-center justify-between">
                    <Link href="/" className="flex items-center gap-2 text-xl font-display font-semibold text-brand-600">
                        <Image src="/logo/rubroicono.png" alt="Mirubro Logo" width={32} height={32} />
                        Mirubro
                    </Link>
                    <nav className="flex gap-6 text-sm font-medium text-slate-700">
                        {marketingLinks.map((link) => (
                            <Link key={link.href} href={link.href} className="hover:text-brand-600">
                                {link.label}
                            </Link>
                        ))}
                    </nav>
                </div>
            </MarketingContainer>
        </header>
    );
}
