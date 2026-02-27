import Image from 'next/image';
import Link from 'next/link';
import type { Route } from 'next';
import type { BlogPost } from '../_data';

interface BlogCardProps {
    post: BlogPost;
}

const dateFormatter = new Intl.DateTimeFormat('es', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
});

/**
 * Card individual de post de blog.
 *
 * Altura fija por breakpoint (h-[420px] / sm:h-[440px] / lg:h-[460px]).
 *
 * Estructura de links — tres links independientes (válido HTML, no anidados):
 *   1. Imágen  → /blog/:slug
 *   2. Título  → /blog/:slug
 *   3. "Leer más →" footer → /blog/:slug
 *
 * Hover: shadow (no borde extra) para evitar layout shift de 1 px.
 */
export function BlogCard({ post }: BlogCardProps) {
    const formattedDate = dateFormatter.format(new Date(post.date));
    const href = `/blog/${post.slug}` as Route;

    return (
        <article className="group flex h-[420px] flex-col overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm transition-shadow duration-200 hover:shadow-md sm:h-[440px] lg:h-[460px]">
            {/* Cover image — link 1 */}
            <Link
                href={href}
                tabIndex={-1}
                aria-hidden="true"
                className="relative block h-[180px] w-full shrink-0 overflow-hidden sm:h-[200px] lg:h-[210px]"
            >
                <Image
                    src={post.coverImageUrl}
                    alt=""
                    fill
                    loading="lazy"
                    className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
                    sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                />
            </Link>

            {/* Content — ocupa el espacio restante */}
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-4 lg:p-5">
                {/* Meta row */}
                <div className="flex shrink-0 items-center justify-between text-xs text-zinc-500">
                    <span>Lectura: {post.readingTime}</span>
                    <span className="font-semibold uppercase tracking-[0.18em] text-primary">
                        {post.sourceLabel}
                    </span>
                </div>

                {/* Title — link 2; h3 (página tiene h1 y la sección tiene h2) */}
                <h3 className="mt-2 line-clamp-2 shrink-0 text-sm font-semibold leading-snug text-zinc-900 transition-colors group-hover:text-primary sm:text-base">
                    <Link
                        href={href}
                        className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
                    >
                        {post.title}
                    </Link>
                </h3>

                {/* Excerpt — 2 líneas en mobile, 3 en sm+ */}
                <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-zinc-600 sm:line-clamp-3 sm:text-sm">
                    {post.excerpt}
                </p>

                {/* Footer: fecha + CTA */}
                <div className="mt-auto flex shrink-0 items-center justify-between pt-3">
                    <time dateTime={post.date} className="text-xs text-zinc-400">
                        {formattedDate}
                    </time>
                    {/* Link 3 — CTA visible */}
                    <Link
                        href={href}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-primary transition-colors hover:text-primary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
                        aria-label={`Leer más: ${post.title}`}
                    >
                        Leer más
                        <span aria-hidden="true">→</span>
                    </Link>
                </div>
            </div>
        </article>
    );
}
