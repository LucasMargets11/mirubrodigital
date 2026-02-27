import Image from 'next/image';
import Link from 'next/link';
import type { Route } from 'next';
import { Button } from '@/components/ui/button';
import type { BlogPost } from '../_data';

interface BlogFeaturedHeroProps {
    post: BlogPost;
}

const dateFormatter = new Intl.DateTimeFormat('es', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
});

/**
 * Hero compacto para el post destacado del blog.
 * Título del post = h2 (la página provee el h1 "Blog de Mirubro").
 * Diseño: 2 columnas en desktop (imagen izq · texto der), stack en mobile.
 * Alto máximo aprox. 440 px en desktop — no ocupa pantalla completa.
 */
export function BlogFeaturedHero({ post }: BlogFeaturedHeroProps) {
    const formattedDate = dateFormatter.format(new Date(post.date));
    const href = `/blog/${post.slug}` as Route;

    return (
        <section
            aria-labelledby="featured-post-title"
            className="border-b border-zinc-100 py-10 lg:py-14"
        >
            <div className="mx-auto max-w-7xl px-6 lg:px-10">
                {/* Section eyebrow */}
                <p className="mb-6 text-sm font-semibold uppercase tracking-[0.25em] text-primary">
                    Artículo destacado
                </p>

                <div className="grid items-center gap-8 lg:grid-cols-2 lg:gap-12">
                    {/* ── Left: cover image — link 1 ── */}
                    <Link
                        href={href}
                        aria-hidden="true"
                        tabIndex={-1}
                        className="relative block aspect-[16/10] w-full overflow-hidden rounded-2xl shadow-md"
                    >
                        <Image
                            src={post.coverImageUrl}
                            alt=""
                            fill
                            className="object-cover"
                            sizes="(max-width: 1024px) 100vw, 50vw"
                            priority
                        />
                    </Link>

                    {/* ── Right: content ── */}
                    <div className="space-y-5">
                        {/* Meta row: reading time + date */}
                        <div className="flex items-center justify-between text-sm text-zinc-500">
                            <span className="flex items-center gap-1.5">
                                <span
                                    className="h-1.5 w-1.5 rounded-full bg-primary"
                                    aria-hidden="true"
                                />
                                Lectura: {post.readingTime}
                            </span>
                            <time dateTime={post.date}>{formattedDate}</time>
                        </div>

                        {/* Title — link 2; h2 porque h1 está en la página */}
                        <h2
                            id="featured-post-title"
                            className="text-3xl font-display font-bold leading-tight text-zinc-900 sm:text-4xl"
                        >
                            <Link
                                href={href}
                                className="hover:text-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
                            >
                                {post.title}
                            </Link>
                        </h2>

                        {/* Excerpt */}
                        <p className="text-base leading-relaxed text-zinc-600">
                            {post.excerpt}
                        </p>

                        {/* CTAs */}
                        <div className="flex flex-wrap items-center gap-3">
                            <Button asChild>
                                <Link
                                    href={href}
                                    aria-label={`Leer artículo: ${post.title}`}
                                >
                                    Leer artículo
                                </Link>
                            </Button>
                            <Link
                                href="/blog"
                                className="text-sm font-medium text-zinc-500 transition-colors hover:text-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
                            >
                                Ver todos los artículos
                            </Link>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
