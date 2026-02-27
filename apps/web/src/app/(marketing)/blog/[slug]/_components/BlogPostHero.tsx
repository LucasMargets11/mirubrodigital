import Image from 'next/image';
import Link from 'next/link';
import type { BlogPost } from '../../_data';

interface BlogPostHeroProps {
    post: BlogPost;
    formattedDate: string;
}

/**
 * Header editorial del post.
 *
 * Layout:
 *   - Bloque de texto (max-w-[900px]): meta 3 columnas + h1 dominante
 *   - Imagen más angosta (max-w-[780px]) para que el título tenga más peso visual
 *
 * Meta row (desktop):  fecha (izq) | MIRUBRO (centro) | Lectura (der)
 * Meta row (mobile):   fecha (izq) / lectura (der)  +  MIRUBRO segunda línea
 */
export function BlogPostHero({ post, formattedDate }: BlogPostHeroProps) {
    return (
        <header className="w-full px-6 pb-10 pt-4 lg:px-10">
            {/* ── Bloque texto — más ancho que la imagen ── */}
            <div className="mx-auto max-w-[900px]">

                {/* Meta bar — desktop: 3 cols, mobile: 2 filas */}
                <div className="mb-6 text-sm text-zinc-500">
                    {/* Desktop: grid de 3 columnas equidistantes */}
                    <div className="hidden items-center sm:grid sm:grid-cols-[1fr_auto_1fr]">
                        <time dateTime={post.date} className="text-left">
                            {formattedDate}
                        </time>
                        <Link
                            href="/blog"
                            className="px-4 text-center font-semibold uppercase tracking-widest text-zinc-700 transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
                        >
                            {post.sourceLabel}
                        </Link>
                        <span className="text-right">Lectura: {post.readingTime}</span>
                    </div>

                    {/* Mobile: fecha/lectura en fila, MIRUBRO debajo */}
                    <div className="flex flex-col gap-1 sm:hidden">
                        <div className="flex justify-between">
                            <time dateTime={post.date}>{formattedDate}</time>
                            <span>Lectura: {post.readingTime}</span>
                        </div>
                        <Link
                            href="/blog"
                            className="self-start font-semibold uppercase tracking-widest text-zinc-700 transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
                        >
                            {post.sourceLabel}
                        </Link>
                    </div>
                </div>

                {/* H1 — elemento dominante */}
                <h1 className="mb-10 font-display text-3xl font-bold leading-tight text-zinc-900 sm:text-4xl lg:text-5xl">
                    {post.title}
                </h1>
            </div>

            {/* ── Imagen — más angosta que el texto ── */}
            <div className="mx-auto max-w-[780px]">
                <div className="relative aspect-[16/9] w-full overflow-hidden rounded-2xl shadow-md">
                    <Image
                        src={post.coverImageUrl}
                        alt={post.title}
                        fill
                        priority
                        className="object-cover"
                        sizes="(max-width: 768px) 100vw, 780px"
                    />
                </div>
            </div>
        </header>
    );
}
