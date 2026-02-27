import Link from 'next/link';
import type { Route } from 'next';
import type { BlogPost, BlogCategory } from '../_data';
import { BlogCard } from './BlogCard';

interface BlogGridProps {
    posts: BlogPost[];
    categories: BlogCategory[];
    activeCategory?: string;
}

/**
 * Grid responsivo de posts del blog con filtro de categorías.
 * 3 columnas en desktop · 2 en tablet · 1 en mobile.
 *
 * El filtro funciona con query params (/blog?categoria=inventario) —
 * links estáticos para que Google pueda crawlear cada URL de categoría.
 */
export function BlogGrid({ posts, categories, activeCategory }: BlogGridProps) {
    return (
        <section aria-label="Artículos recientes" className="py-12">
            <div className="mx-auto max-w-7xl px-6 lg:px-10">
                {/* Section header */}
                <div className="mb-6">
                    <p className="mb-1 text-sm font-semibold uppercase tracking-[0.25em] text-primary">
                        Blog
                    </p>
                    <h2 className="text-2xl font-display font-semibold text-zinc-900">
                        Artículos recientes
                    </h2>
                </div>

                {/* Category filter pills */}
                <nav aria-label="Filtrar por tema" className="mb-8">
                    <ul role="list" className="flex flex-wrap gap-2">
                        <li>
                            <Link
                                href="/blog" 
                                className={[
                                    'inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold transition-colors',
                                    !activeCategory
                                        ? 'bg-primary text-white'
                                        : 'border border-zinc-200 bg-white text-zinc-600 hover:border-primary/50 hover:text-primary',
                                ].join(' ')}
                                aria-current={!activeCategory ? 'page' : undefined}
                            >
                                Todos
                            </Link>
                        </li>
                        {categories.map((cat) => (
                            <li key={cat.slug}>
                                <Link
                                    href={`/blog?categoria=${cat.slug}` as Route}
                                    className={[
                                        'inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold transition-colors',
                                        activeCategory === cat.slug
                                            ? 'bg-primary text-white'
                                            : 'border border-zinc-200 bg-white text-zinc-600 hover:border-primary/50 hover:text-primary',
                                    ].join(' ')}
                                    aria-current={activeCategory === cat.slug ? 'page' : undefined}
                                >
                                    {cat.label}
                                </Link>
                            </li>
                        ))}
                    </ul>
                </nav>

                {/* Grid — las li usan h-full para que la card llene la fila */}
                {posts.length === 0 ? (
                    <p className="py-16 text-center text-sm text-zinc-500">
                        No hay artículos en esta categoría por el momento.
                    </p>
                ) : (
                    <ul role="list" className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                        {posts.map((post) => (
                            <li key={post.slug} className="h-full">
                                <BlogCard post={post} />
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </section>
    );
}
