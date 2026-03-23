import type { Metadata } from 'next';
import { BlogFeaturedHero } from './_components/BlogFeaturedHero';
import { BlogGrid } from './_components/BlogGrid';
import { getBlogListing, getBlogCategories } from './_api';

const SITE_URL = 'https://www.mirubro.com';
const BLOG_URL = `${SITE_URL}/blog`;

export const metadata: Metadata = {
    title: 'Blog | Mirubro',
    description:
        'Recursos, guías y novedades sobre gestión de negocios, inventario, ventas y tecnología para PYMEs.',
    alternates: { canonical: BLOG_URL },
    openGraph: {
        title: 'Blog | Mirubro',
        description:
            'Recursos, guías y novedades sobre gestión de negocios, inventario, ventas y tecnología para PYMEs.',
        url: BLOG_URL,
        siteName: 'Mirubro',
        type: 'website',
        locale: 'es_AR',
    },
    twitter: {
        card: 'summary_large_image',
        title: 'Blog | Mirubro',
        description:
            'Recursos, guías y novedades sobre gestión de negocios, inventario, ventas y tecnología para PYMEs.',
    },
};

/** JSON-LD: Blog + ItemList of published posts. */
function BlogJsonLd({ posts }: { posts: Array<{ title: string; excerpt: string; slug: string; date: string; coverImageUrl: string }> }) {
    const schema = {
        '@context': 'https://schema.org',
        '@type': 'Blog',
        name: 'Blog de Mirubro',
        description:
            'Recursos y guías sobre gestión de negocios, inventario, ventas y tecnología para PYMEs.',
        url: BLOG_URL,
        publisher: {
            '@type': 'Organization',
            name: 'Mirubro',
            url: SITE_URL,
        },
        blogPost: posts.map((post) => ({
            '@type': 'BlogPosting',
            headline: post.title,
            description: post.excerpt,
            url: `${BLOG_URL}/${post.slug}`,
            datePublished: post.date,
            image: post.coverImageUrl.startsWith('/') ? `${SITE_URL}${post.coverImageUrl}` : post.coverImageUrl,
            author: { '@type': 'Organization', name: 'Mirubro' },
        })),
    };
    return (
        <script
            type="application/ld+json"
            dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
        />
    );
}

interface BlogPageProps {
    searchParams: Promise<{ categoria?: string; page?: string }>;
}

export default async function BlogPage({ searchParams }: BlogPageProps) {
    const { categoria, page: pageParam } = await searchParams;
    const currentPage = Math.max(1, parseInt(pageParam ?? '1', 10) || 1);

    const [listing, categories] = await Promise.all([
        getBlogListing({ category: categoria, page: currentPage }),
        getBlogCategories(),
    ]);

    const { posts, totalPages } = listing;
    const isFirstPage = currentPage === 1;
    const featuredPost = isFirstPage ? (posts[0] ?? null) : null;
    const gridPosts = isFirstPage && featuredPost ? posts.slice(1) : posts;

    return (
        <>
            <BlogJsonLd posts={posts} />

            {/* Page header */}
            <div className="border-b border-zinc-100 bg-slate-50/60 py-8">
                <div className="mx-auto max-w-7xl px-6 lg:px-10">
                    <h1 className="text-4xl font-display font-bold text-zinc-900">
                        Blog de Mirubro
                    </h1>
                    <p className="mt-2 text-base text-zinc-600">
                        Guías, recursos y novedades para hacer crecer tu negocio.
                    </p>
                </div>
            </div>

            <main id="main-content">
                {featuredPost && <BlogFeaturedHero post={featuredPost} />}
                <BlogGrid
                    posts={gridPosts}
                    categories={categories}
                    activeCategory={categoria}
                />

                {/* Pagination */}
                {totalPages > 1 && (
                    <BlogPagination
                        currentPage={currentPage}
                        totalPages={totalPages}
                        categoria={categoria}
                    />
                )}
            </main>
        </>
    );
}

// ── Pagination ───────────────────────────────────────────────────────────────

function BlogPagination({
    currentPage,
    totalPages,
    categoria,
}: {
    currentPage: number;
    totalPages: number;
    categoria?: string;
}) {
    function buildHref(page: number) {
        const params = new URLSearchParams();
        if (categoria) params.set('categoria', categoria);
        if (page > 1) params.set('page', String(page));
        const qs = params.toString();
        return `/blog${qs ? `?${qs}` : ''}`;
    }

    /** Visible page numbers: always show first, last, current ±1, with ellipses. */
    function getPageNumbers(): (number | 'ellipsis')[] {
        if (totalPages <= 7) {
            return Array.from({ length: totalPages }, (_, i) => i + 1);
        }
        const pages = new Set<number>([1, totalPages]);
        for (let d = -1; d <= 1; d++) {
            const p = currentPage + d;
            if (p >= 1 && p <= totalPages) pages.add(p);
        }
        const sorted = [...pages].sort((a, b) => a - b);
        const result: (number | 'ellipsis')[] = [];
        for (let i = 0; i < sorted.length; i++) {
            if (i > 0 && sorted[i]! - sorted[i - 1]! > 1) {
                result.push('ellipsis');
            }
            result.push(sorted[i]!);
        }
        return result;
    }

    const pages = getPageNumbers();

    return (
        <nav
            aria-label="Paginación del blog"
            className="flex items-center justify-center gap-1 pb-16 pt-4"
        >
            {/* Previous */}
            {currentPage > 1 ? (
                <a
                    href={buildHref(currentPage - 1)}
                    className="inline-flex items-center rounded-lg px-3 py-2 text-sm font-medium text-zinc-600 hover:bg-zinc-100"
                    aria-label="Página anterior"
                >
                    <svg className="mr-1 h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" /></svg>
                    Anterior
                </a>
            ) : (
                <span className="inline-flex items-center rounded-lg px-3 py-2 text-sm font-medium text-zinc-300" aria-disabled="true">
                    <svg className="mr-1 h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" /></svg>
                    Anterior
                </span>
            )}

            {/* Page numbers */}
            {pages.map((p, i) =>
                p === 'ellipsis' ? (
                    <span key={`e-${i}`} className="px-2 text-zinc-400">
                        &hellip;
                    </span>
                ) : p === currentPage ? (
                    <span
                        key={p}
                        className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-sm font-semibold text-white"
                        aria-current="page"
                    >
                        {p}
                    </span>
                ) : (
                    <a
                        key={p}
                        href={buildHref(p)}
                        className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-sm font-medium text-zinc-600 hover:bg-zinc-100"
                    >
                        {p}
                    </a>
                ),
            )}

            {/* Next */}
            {currentPage < totalPages ? (
                <a
                    href={buildHref(currentPage + 1)}
                    className="inline-flex items-center rounded-lg px-3 py-2 text-sm font-medium text-zinc-600 hover:bg-zinc-100"
                    aria-label="Página siguiente"
                >
                    Siguiente
                    <svg className="ml-1 h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" /></svg>
                </a>
            ) : (
                <span className="inline-flex items-center rounded-lg px-3 py-2 text-sm font-medium text-zinc-300" aria-disabled="true">
                    Siguiente
                    <svg className="ml-1 h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" /></svg>
                </span>
            )}
        </nav>
    );
}
