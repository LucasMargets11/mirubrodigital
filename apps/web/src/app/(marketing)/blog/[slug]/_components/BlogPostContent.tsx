import Image from 'next/image';
import Link from 'next/link';
import type { ContentBlock } from '../../_data';

interface BlogPostContentProps {
    excerpt: string;
    /** Legacy: array of plain paragraphs usado por posts sin bodyContent. */
    paragraphs?: string[];
    /** Bloques de contenido rico para posts nuevos. */
    bodyContent?: ContentBlock[];
}

/** Renderiza un bloque de contenido estructurado. */
function Block({ block }: { block: ContentBlock }) {
    switch (block.type) {
        case 'h2':
            return (
                <h2 className="mb-3 mt-10 font-display text-xl font-bold leading-snug text-zinc-900 sm:text-2xl first:mt-0">
                    {block.text}
                </h2>
            );
        case 'h3':
            return (
                <h3 className="mb-2 mt-7 font-display text-lg font-semibold leading-snug text-zinc-800">
                    {block.text}
                </h3>
            );
        case 'p':
            return (
                <p className="text-base leading-[1.8] text-zinc-600">
                    {block.text}
                </p>
            );
        case 'ul':
            return (
                <ul className="space-y-2 pl-2">
                    {block.items.map((item, i) => (
                        <li key={i} className="flex gap-3 text-base leading-[1.7] text-zinc-600">
                            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-zinc-400" aria-hidden="true" />
                            {item}
                        </li>
                    ))}
                </ul>
            );
        case 'check':
            return (
                <ul className="space-y-2 pl-2">
                    {block.items.map((item, i) => (
                        <li key={i} className="flex gap-3 text-base leading-[1.7] text-zinc-600">
                            <span className="mt-0.5 shrink-0 text-emerald-500" aria-hidden="true">✓</span>
                            {item}
                        </li>
                    ))}
                </ul>
            );
        case 'cta':
            return (
                <div className="my-10 rounded-2xl border border-zinc-100 bg-slate-50 px-6 py-8 text-center shadow-sm">
                    <p className="mb-5 text-base font-medium leading-relaxed text-zinc-700">
                        {block.text}
                    </p>
                    <Link
                        href={block.href as '/'}
                        className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-7 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600 focus-visible:ring-offset-2"
                    >
                        {block.buttonLabel}
                    </Link>
                </div>
            );
        case 'faq':
            return (
                <div className="mt-10 space-y-5">
                    <h2 className="font-display text-xl font-bold text-zinc-900 sm:text-2xl">Preguntas frecuentes</h2>
                    <dl className="space-y-4">
                        {block.items.map((item, i) => (
                            <div key={i} className="rounded-xl border border-zinc-100 bg-slate-50/70 px-5 py-4">
                                <dt className="mb-1.5 text-sm font-semibold text-zinc-900">{item.q}</dt>
                                <dd className="text-sm leading-relaxed text-zinc-600">{item.a}</dd>
                            </div>
                        ))}
                    </dl>
                </div>
            );
        default:
            return null;
    }
}

/**
 * Cuerpo editorial del artículo.
 * Soporta dos modos:
 *   1. bodyContent: array de ContentBlock (posts nuevos con contenido rico)
 *   2. paragraphs: array de strings planos (posts legacy / placeholder)
 */
export function BlogPostContent({ excerpt, paragraphs, bodyContent }: BlogPostContentProps) {
    return (
        <div className="min-w-0 flex-1">
            {/* Lead / excerpt */}
            <p className="mb-8 text-lg font-medium leading-relaxed text-zinc-700 [text-wrap:balance]">
                {excerpt}
            </p>

            {/* Rich content blocks (posts nuevos) */}
            {bodyContent && bodyContent.length > 0 ? (
                <div className="space-y-5">
                    {bodyContent.map((block, i) => (
                        <Block key={i} block={block} />
                    ))}
                </div>
            ) : (
                /* Legacy: plain paragraphs */
                <div className="space-y-5">
                    {(paragraphs ?? []).map((para, i) => (
                        <p key={i} className="text-base leading-[1.8] text-zinc-600">
                            {para}
                        </p>
                    ))}
                </div>
            )}

            {/* Separator + Mirubro logo — cierre del artículo */}
            <div className="mt-14 flex flex-col items-center gap-4">
                <div className="h-px w-24 bg-zinc-200" aria-hidden="true" />
                <div className="flex flex-col items-center gap-2 text-zinc-400">
                    <Image
                        src="/logo/rubroicono.png"
                        alt="Mirubro"
                        width={36}
                        height={36}
                        className="opacity-40"
                    />
                    <p className="text-xs font-semibold uppercase tracking-[0.25em]">Mirubro</p>
                </div>
            </div>
        </div>
    );
}
