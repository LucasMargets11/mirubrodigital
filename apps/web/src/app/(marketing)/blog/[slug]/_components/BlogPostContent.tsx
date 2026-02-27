import Image from 'next/image';

interface BlogPostContentProps {
    excerpt: string;
    paragraphs: string[];
}

/**
 * Cuerpo editorial del artículo.
 * Usa clases Tailwind para tipografía legible sin depender del plugin prose.
 * Reutilizar/ampliar con bloques desde CMS (H2, blockquote, listas…).
 */
export function BlogPostContent({ excerpt, paragraphs }: BlogPostContentProps) {
    return (
        <div className="min-w-0 flex-1">
            {/* Lead / excerpt */}
            <p className="mb-8 text-lg font-medium leading-relaxed text-zinc-700 [text-wrap:balance]">
                {excerpt}
            </p>

            {/* Body paragraphs */}
            <div className="space-y-5">
                {paragraphs.map((para, i) => (
                    <p key={i} className="text-base leading-[1.8] text-zinc-600">
                        {para}
                    </p>
                ))}
            </div>

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
