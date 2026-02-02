import Link from 'next/link';

interface FooterLinkProps {
    href: string;
    children: React.ReactNode;
}

function FooterLink({ href, children }: FooterLinkProps) {
    return (
        <li className="mb-3">
            <Link 
                href={href} 
                className="text-sm text-slate-500 transition-colors hover:text-blue-700 hover:underline"
            >
                {children}
            </Link>
        </li>
    );
}

interface FooterSectionProps {
    title: string;
    children: React.ReactNode;
}

function FooterSection({ title, children }: FooterSectionProps) {
    return (
        <div className="flex flex-col">
            <h4 className="mb-6 text-sm font-semibold tracking-wider text-slate-900 uppercase">
                {title}
            </h4>
            <ul className="list-none p-0 m-0">
                {children}
            </ul>
        </div>
    );
}

import { MarketingContainer } from '@/components/ui/marketing-container';

export function MarketingFooter() {
    const year = new Date().getFullYear();

    return (
        <footer className="bg-white text-slate-600 border-t border-slate-200">
            <MarketingContainer className="py-16 lg:py-20">
                <div className="grid grid-cols-1 gap-12 lg:grid-cols-5 lg:gap-8">
                    {/* Brand Column (2 cols) */}
                    <div className="lg:col-span-2 flex flex-col items-start gap-6">
                        <div>
                            <h3 className="text-xl font-bold text-slate-900 mb-2">Mirubro Digital</h3>
                            <p className="text-sm text-slate-500 leading-relaxed max-w-sm">
                                Plataforma para restaurantes y comercios: stock, pedidos, caja y operación en un solo lugar.
                            </p>
                        </div>
                        
                        <Link 
                            href="/planes" 
                            className="inline-flex items-center justify-center rounded-xl border border-blue-600 bg-transparent px-6 py-2.5 text-sm font-medium text-blue-700 transition-all hover:bg-blue-50"
                        >
                            Ver planes
                        </Link>
                    </div>

                    {/* Links Columns */}
                    <FooterSection title="Productos">
                        <FooterLink href="/restaurante-inteligente">Restaurante Inteligente</FooterLink>
                        <FooterLink href="/gestion-comercial">Gestión Comercial</FooterLink>
                        <FooterLink href="/qr-menu">Menú QR</FooterLink>
                        <FooterLink href="/integraciones">Integraciones</FooterLink>
                    </FooterSection>

                    <FooterSection title="Soluciones">
                        <FooterLink href="/soluciones/restaurantes">Restaurantes</FooterLink>
                        <FooterLink href="/soluciones/cafeterias">Cafeterías</FooterLink>
                        <FooterLink href="/soluciones/kioscos">Kioscos</FooterLink>
                        <FooterLink href="/soluciones/take-away">Take Away</FooterLink>
                    </FooterSection>

                    <FooterSection title="Recursos">
                        <FooterLink href="/vlog">Vlog</FooterLink>
                        <FooterLink href="/guias">Guías</FooterLink>
                        <FooterLink href="/casos">Casos de éxito</FooterLink>
                        <FooterLink href="/descargables">Descargables</FooterLink>
                    </FooterSection>
                </div>

                {/* Bottom Strip */}
                <div className="mt-16 pt-8 border-t border-slate-100 flex flex-col md:flex-row justify-between items-center gap-4 text-xs text-slate-400">
                    <p>© {year} Mirubro Digital. Todos los derechos reservados.</p>
                    <div className="flex gap-6">
                        <Link href="/privacidad" className="hover:text-blue-700 transition-colors">Privacidad</Link>
                        <Link href="/terminos" className="hover:text-blue-700 transition-colors">Términos</Link>
                        <Link href="/contacto" className="hover:text-blue-700 transition-colors">Contacto</Link>
                    </div>
                </div>
            </MarketingContainer>
        </footer>
    );
}
