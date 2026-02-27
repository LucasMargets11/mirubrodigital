import type { BlogPost } from '../../_data';
import { BlogCard } from '../../_components/BlogCard';

interface RelatedPostsProps {
    posts: BlogPost[];
}

/**
 * Sección de posts relacionados al final del artículo.
 * Reutiliza BlogCard exactamente igual que en /blog,
 * mismo alto fijo, mismo grid responsive.
 */
export function RelatedPosts({ posts }: RelatedPostsProps) {
    if (posts.length === 0) return null;

    return (
        <section aria-labelledby="related-posts-heading" className="border-t border-zinc-100 bg-slate-50/60 py-14">
            <div className="mx-auto max-w-7xl px-6 lg:px-10">
                <div className="mb-8">
                    <p className="mb-1 text-sm font-semibold uppercase tracking-[0.25em] text-primary">
                        Seguí leyendo
                    </p>
                    <h2
                        id="related-posts-heading"
                        className="text-2xl font-display font-semibold text-zinc-900"
                    >
                        Posts relacionados
                    </h2>
                </div>

                <ul
                    role="list"
                    className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3"
                >
                    {posts.map((post) => (
                        <li key={post.slug} className="h-full">
                            <BlogCard post={post} />
                        </li>
                    ))}
                </ul>
            </div>
        </section>
    );
}
