'use client';

import { useState, useEffect } from 'react';

interface ShareSidebarProps {
    title: string;
    /**
     * 'mobile'  — fila horizontal, visible solo en mobile (lg:hidden)
     * 'desktop' — columna sticky, visible solo en desktop (hidden lg:flex)
     */
    variant: 'mobile' | 'desktop';
}

interface ShareItem {
    key: string;
    label: string;
    icon: React.ReactNode;
    action: (title: string) => void;
}

function IconLinkedIn() {
    return (
        <svg viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5" aria-hidden="true">
            <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
        </svg>
    );
}

function IconFacebook() {
    return (
        <svg viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5" aria-hidden="true">
            <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
        </svg>
    );
}

function IconX() {
    return (
        <svg viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5" aria-hidden="true">
            <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.736-8.857L1.254 2.25H8.08l4.266 5.638L18.245 2.25zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
        </svg>
    );
}

function IconWhatsApp() {
    return (
        <svg viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5" aria-hidden="true">
            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413z" />
        </svg>
    );
}

function IconMail() {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5" aria-hidden="true">
            <rect width="20" height="16" x="2" y="4" rx="2" />
            <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
        </svg>
    );
}

function IconLink() {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5" aria-hidden="true">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </svg>
    );
}

function IconCheck() {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5" aria-hidden="true">
            <path d="M20 6 9 17l-5-5" />
        </svg>
    );
}

const BUTTON_CLASS =
    'flex items-center justify-center rounded-full p-2.5 text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2';

/**
 * Sidebar de compartir — sticky durante el scroll en desktop.
 * En mobile se convierte en una fila horizontal debajo del hero.
 *
 * Los links de redes se construyen en el cliente para leer window.location.href.
 * Se marca 'use client' para el Clipboard API también.
 */
export function ShareSidebar({ title, variant }: ShareSidebarProps) {
    const [copied, setCopied] = useState(false);
    // url starts as '' on both SSR and initial client render to avoid
    // hydration mismatch; populated after mount via useEffect.
    const [url, setUrl] = useState('');

    useEffect(() => {
        setUrl(window.location.href);
    }, []);

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(window.location.href);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // fallback silencioso
        }
    };

    const socialLinks = [
        {
            key: 'linkedin',
            label: 'Compartir en LinkedIn',
            href: `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(url)}`,
            icon: <IconLinkedIn />,
        },
        {
            key: 'facebook',
            label: 'Compartir en Facebook',
            href: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}`,
            icon: <IconFacebook />,
        },
        {
            key: 'twitter',
            label: 'Compartir en X (Twitter)',
            href: `https://twitter.com/intent/tweet?text=${encodeURIComponent(title)}&url=${encodeURIComponent(url)}`,
            icon: <IconX />,
        },
        {
            key: 'whatsapp',
            label: 'Compartir en WhatsApp',
            href: `https://wa.me/?text=${encodeURIComponent(`${title} ${url}`)}`,
            icon: <IconWhatsApp />,
        },
        {
            key: 'email',
            label: 'Compartir por correo',
            href: `mailto:?subject=${encodeURIComponent(title)}&body=${encodeURIComponent(url)}`,
            icon: <IconMail />,
        },
    ];

    const buttons = (vertical: boolean) => (
        <>
            {socialLinks.map(({ key, label, href, icon }) => (
                <a
                    key={key}
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={label}
                    className={BUTTON_CLASS}
                >
                    {icon}
                </a>
            ))}

            {/* Separador sutil */}
            <span
                aria-hidden="true"
                className={vertical ? 'mx-auto h-px w-6 bg-zinc-200' : 'h-6 w-px bg-zinc-200'}
            />

            {/* Copiar link */}
            <button
                type="button"
                onClick={handleCopy}
                aria-label={copied ? 'Link copiado' : 'Copiar link'}
                title={copied ? 'Copiado' : 'Copiar link'}
                className={[BUTTON_CLASS, copied ? 'text-emerald-600' : ''].join(' ')}
            >
                {copied ? <IconCheck /> : <IconLink />}
            </button>
        </>
    );

    return (
        <>
            {/* ── Desktop: columna sticky izquierda ── */}
            {variant === 'desktop' && (
                <aside
                    aria-label="Compartir artículo"
                    className="hidden lg:flex lg:w-14 lg:shrink-0 lg:flex-col lg:items-center lg:gap-2 lg:pt-1"
                    style={{ position: 'sticky', top: '80px', alignSelf: 'flex-start' }}
                >
                    <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-zinc-400">
                        Compartir
                    </p>
                    {buttons(true)}
                </aside>
            )}

            {/* ── Mobile: fila horizontal debajo del hero ── */}
            {variant === 'mobile' && (
                <div
                    aria-label="Compartir artículo"
                    className="flex items-center justify-center gap-1 border-b border-zinc-100 py-4"
                >
                    <p className="mr-2 text-xs font-semibold uppercase tracking-widest text-zinc-400">
                        Compartir
                    </p>
                    {buttons(false)}
                </div>
            )}
        </>
    );
}
