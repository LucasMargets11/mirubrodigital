import Link from 'next/link';
import { SiteContainer } from '@/components/layout/site-container';

interface FooterLinkProps {
    href: string;
    children: React.ReactNode;
}

function FooterLink({ href, children }: FooterLinkProps) {
    return (
        <li>
            <Link
                href={href}
                className="text-sm leading-7 text-slate-500 transition-colors hover:text-primary"
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
            <h4 className="mb-4 text-xs font-semibold uppercase tracking-widest text-slate-900">
                {title}
            </h4>
            <ul className="m-0 list-none p-0 space-y-0">
                {children}
            </ul>
        </div>
    );
}

/**
 * Footer de marketing.
 *
 * Layout espeja el header:
 *   header → [logo | nav links]  (flex justify-between dentro de SiteContainer)
 *   footer → [branding | cols]   (flex justify-between dentro de SiteContainer)
 *
 * Resultado: "Mirubro Digital" arranca en el mismo x que el logo,
 * y "Recursos" termina en el mismo x que "Ingresar".
 */
export function MarketingFooter() {
    const year = new Date().getFullYear();

    return (
        <footer className="border-t border-slate-200 bg-white text-slate-600">
            <SiteContainer className="py-16 lg:py-20">

                {/*
                 * Zona principal — mismo modelo flex justify-between que el header.
                 * Mobile: stack vertical.
                 * Desktop: [branding izq] ←→ [3 cols der]
                 */}
                <div className="flex flex-col gap-10 lg:flex-row lg:justify-between">

                    {/* ── Zona izquierda: Branding (alineada con el logo) ── */}
                    <div className="flex flex-col gap-5 lg:max-w-[260px]">
                        <div>
                            <h3 className="mb-2 text-base font-bold text-slate-900">Mirubro Digital</h3>
                            <p className="text-sm leading-relaxed text-slate-500">
                                Plataforma para restaurantes y comercios: stock, pedidos, caja y operación en un solo lugar.
                            </p>
                        </div>
                        <Link
                            href="/planes"
                            className="inline-flex w-fit items-center justify-center rounded-xl border border-primary bg-transparent px-5 py-2 text-sm font-medium text-primary transition-all hover:bg-primary/5"
                        >
                            Ver planes
                        </Link>
                    </div>

                    {/*
                     * ── Zona derecha: columnas de links (alineadas con el nav) ──
                     * grid-cols-2 en mobile/tablet → grid-cols-3 en desktop.
                     * No tiene ml-auto extra; justify-between del padre la empuja al borde derecho.
                     */}
                    <div className="grid grid-cols-2 gap-x-10 gap-y-8 sm:gap-x-16 lg:grid-cols-3 lg:gap-x-20">
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
                            <FooterLink href="/blog">Blog</FooterLink>
                            <FooterLink href="/guias">Guías</FooterLink>
                            <FooterLink href="/casos">Casos de éxito</FooterLink>
                            <FooterLink href="/descargables">Descargables</FooterLink>
                        </FooterSection>
                    </div>
                </div>

                {/* Franja legal */}
                <div className="mt-16 flex flex-col items-start gap-4 border-t border-slate-100 pt-8 md:flex-row md:items-center md:justify-between">
                    <p className="text-xs text-slate-400">© {year} Mirubro Digital. Todos los derechos reservados.</p>
                    <div className="flex gap-6 text-xs text-slate-400">
                        <Link href="/privacidad" className="transition-colors hover:text-primary">Privacidad</Link>
                        <Link href="/terminos" className="transition-colors hover:text-primary">Términos</Link>
                        <Link href="/contacto" className="transition-colors hover:text-primary">Contacto</Link>
                    </div>
                </div>

            </SiteContainer>
        </footer>
    );
}
