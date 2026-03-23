import Link from 'next/link';
import { Instagram } from 'lucide-react';
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
                className="text-sm leading-7 text-slate-500 transition-colors hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 rounded-sm"
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

export function MarketingFooter() {
    const year = new Date().getFullYear();

    return (
        <footer className="border-t border-slate-200 bg-white text-slate-600">
            <SiteContainer className="py-16 lg:py-20">

                <div className="flex flex-col gap-10 lg:flex-row lg:justify-between">

                    {/* ── Branding (izquierda) ── */}
                    <div className="flex flex-col gap-6 lg:max-w-[300px]">
                        <div>
                            <h3 className="mb-2 text-base font-bold text-slate-900">MiRubro Digital</h3>
                            <p className="text-sm leading-relaxed text-slate-500">
                                Software y herramientas digitales para comercios y locales.
                                Simplificá la gestión, compartí tu menú online y conseguí más
                                reseñas para tu negocio.
                            </p>
                        </div>

                        <div className="flex flex-wrap gap-3">
                            <Link
                                href="/pricing"
                                className="inline-flex items-center justify-center rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-brand-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
                            >
                                Ver planes
                            </Link>
                            <Link
                                href="/contacto"
                                className="inline-flex items-center justify-center rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition-all hover:border-brand-300 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
                            >
                                Solicitar demo
                            </Link>
                        </div>

                        <a
                            href="https://www.instagram.com/mirubrodigital/"
                            target="_blank"
                            rel="noopener noreferrer"
                            aria-label="Instagram de MiRubro Digital"
                            className="mt-1 inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
                        >
                            <Instagram className="h-5 w-5" />
                        </a>
                    </div>

                    {/* ── Columnas de navegación (derecha) ── */}
                    <nav aria-label="Navegación del footer">
                        <div className="grid grid-cols-2 gap-x-10 gap-y-8 sm:gap-x-16 lg:grid-cols-3 lg:gap-x-20">
                            <FooterSection title="Productos">
                                <FooterLink href="/services#commercial">Gestión Comercial</FooterLink>
                                <FooterLink href="/services#menu_qr">Menú QR Online</FooterLink>
                                <FooterLink href="/services#qr_reviews">QR para reseñas</FooterLink>
                            </FooterSection>

                            <FooterSection title="Recursos">
                                <FooterLink href="/pricing">Planes</FooterLink>
                                <FooterLink href="/contacto">Contacto</FooterLink>
                                <FooterLink href="/soporte">Soporte</FooterLink>
                                <FooterLink href="/preguntas-frecuentes">Preguntas frecuentes</FooterLink>
                            </FooterSection>

                            <FooterSection title="Empresa">
                                <FooterLink href="/nosotros">Nosotros</FooterLink>
                                <FooterLink href="/blog">Blog</FooterLink>
                                <FooterLink href="/privacidad">Privacidad</FooterLink>
                                <FooterLink href="/terminos">Términos y condiciones</FooterLink>
                            </FooterSection>
                        </div>
                    </nav>
                </div>

                {/* Franja inferior — copyright + VIZION */}
                <div className="mt-16 flex flex-col items-center gap-3 border-t border-slate-100 pt-8 sm:flex-row sm:justify-between sm:gap-0">
                    <p className="text-xs text-slate-400">
                        © {year} MiRubro Digital. Todos los derechos reservados.
                    </p>
                    <p className="text-xs text-slate-400">
                        Desarrollado por{' '}
                        <a
                            href="https://estudiovizion.com"
                            target="_blank"
                            rel="noopener noreferrer"
                            aria-label="Sitio web de Estudio VIZION"
                            className="font-medium text-slate-500 transition-colors hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 rounded-sm"
                        >
                            Estudio VIZION
                        </a>
                    </p>
                </div>

            </SiteContainer>
        </footer>
    );
}
