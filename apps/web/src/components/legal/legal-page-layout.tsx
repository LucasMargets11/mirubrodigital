'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { SiteContainer } from '@/components/layout/site-container';
import { cn } from '@/lib/utils';

type Href = React.ComponentProps<typeof Link>['href'];

/* ─────────────────────────────────────────────
   Tipos
   ───────────────────────────────────────────── */

export interface LegalSection {
    id: string;
    title: string;
    content: React.ReactNode;
}

interface LegalPageLayoutProps {
    title: string;
    subtitle: React.ReactNode;
    lastUpdated: string;
    sections: LegalSection[];
    crossLink?: { href: Href; label: string };
    footerNote?: React.ReactNode;
}

/* ─────────────────────────────────────────────
   Tabla de contenidos
   ───────────────────────────────────────────── */

function TableOfContents({ sections }: { sections: LegalSection[] }) {
    const [activeId, setActiveId] = useState<string | null>(null);

    useEffect(() => {
        const observer = new IntersectionObserver(
            (entries) => {
                for (const entry of entries) {
                    if (entry.isIntersecting) {
                        setActiveId(entry.target.id);
                    }
                }
            },
            { rootMargin: '-80px 0px -60% 0px', threshold: 0 },
        );

        for (const s of sections) {
            const el = document.getElementById(s.id);
            if (el) observer.observe(el);
        }

        return () => observer.disconnect();
    }, [sections]);

    return (
        <nav aria-label="Índice de contenidos" className="hidden xl:block">
            <div className="sticky top-24">
                <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-400">
                    Contenido
                </p>
                <ul className="space-y-1 border-l border-slate-200">
                    {sections.map((s) => (
                        <li key={s.id}>
                            <a
                                href={`#${s.id}`}
                                className={cn(
                                    'block border-l-2 py-1 pl-4 text-sm leading-snug transition-colors',
                                    activeId === s.id
                                        ? 'border-brand-600 font-medium text-brand-600'
                                        : 'border-transparent text-slate-500 hover:text-slate-700',
                                )}
                            >
                                {s.title}
                            </a>
                        </li>
                    ))}
                </ul>
            </div>
        </nav>
    );
}

/* ─────────────────────────────────────────────
   Layout principal
   ───────────────────────────────────────────── */

export function LegalPageLayout({
    title,
    subtitle,
    lastUpdated,
    sections,
    crossLink,
    footerNote,
}: LegalPageLayoutProps) {
    return (
        <SiteContainer as="article" className="py-16 lg:py-24">
            {/* ── Header ── */}
            <header className="mx-auto max-w-3xl text-center">
                <h1 className="font-display text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
                    {title}
                </h1>
                <p className="mt-4 text-base leading-relaxed text-slate-600 sm:text-lg">
                    {subtitle}
                </p>
                <p className="mt-3 text-sm text-slate-400">
                    Última actualización: {lastUpdated}
                </p>
            </header>

            {/* ── Grid: contenido + TOC lateral ── */}
            <div className="mt-12 flex gap-12 lg:mt-16">
                {/* Contenido principal */}
                <div className="min-w-0 flex-1">
                    <div className="mx-auto max-w-3xl space-y-12">
                        {sections.map((section, idx) => (
                            <section
                                key={section.id}
                                id={section.id}
                                className="scroll-mt-24"
                            >
                                <h2 className="font-display text-xl font-semibold text-slate-900 sm:text-2xl">
                                    <span className="mr-2 text-brand-500">
                                        {idx + 1}.
                                    </span>
                                    {section.title}
                                </h2>
                                <div className="mt-4 space-y-4 text-base leading-relaxed text-slate-600">
                                    {section.content}
                                </div>
                                {idx < sections.length - 1 && (
                                    <hr className="mt-12 border-slate-100" />
                                )}
                            </section>
                        ))}

                        {/* ── Link cruzado ── */}
                        {crossLink && (
                            <div className="rounded-lg border border-slate-200 bg-slate-50 px-6 py-5">
                                <p className="text-sm text-slate-600">
                                    Consultá también:{' '}
                                    <Link
                                        href={crossLink.href}
                                        className="font-medium text-brand-600 underline underline-offset-2 hover:text-brand-500"
                                    >
                                        {crossLink.label}
                                    </Link>
                                </p>
                            </div>
                        )}

                        {/* ── Nota de pie ── */}
                        {footerNote && (
                            <p className="text-center text-xs text-slate-400">
                                {footerNote}
                            </p>
                        )}
                    </div>
                </div>

                {/* TOC lateral (solo xl+) */}
                <aside className="hidden w-56 shrink-0 xl:block">
                    <TableOfContents sections={sections} />
                </aside>
            </div>
        </SiteContainer>
    );
}
