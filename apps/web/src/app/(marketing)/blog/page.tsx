import type { Metadata } from 'next';
import { BlogFeaturedHero } from './_components/BlogFeaturedHero';
import { BlogGrid } from './_components/BlogGrid';
import { featuredPost, recentPosts, categories } from './_data';

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
        images: [
            {
                url: featuredPost.coverImageUrl,
                width: 900,
                alt: featuredPost.title,
            },
        ],
        type: 'website',
        locale: 'es_AR',
    },
    twitter: {
        card: 'summary_large_image',
        title: 'Blog | Mirubro',
        description:
            'Recursos, guías y novedades sobre gestión de negocios, inventario, ventas y tecnología para PYMEs.',
        images: [featuredPost.coverImageUrl],
    },
};

/** JSON-LD: Blog + ItemList de posts recientes. */
function BlogJsonLd() {
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
        blogPost: recentPosts.map((post) => ({
            '@type': 'BlogPosting',
            headline: post.title,
            description: post.excerpt,
            url: `${BLOG_URL}/${post.slug}`,
            datePublished: post.date,
            image: post.coverImageUrl,
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
    searchParams: Promise<{ categoria?: string }>;
}

/**
 * Página de listado del blog (/blog).
 *
 * Jerarquía de headings:
 *   h1 → "Blog de Mirubro" (visible, al inicio de la página)
 *   h2 → Título del post destacado (en BlogFeaturedHero)
 *   h2 → "Artículos recientes" (en BlogGrid)
 *   h3 → Título de cada card (en BlogCard)
 */
export default async function BlogPage({ searchParams }: BlogPageProps) {
    const { categoria } = await searchParams;

    const filteredPosts = categoria
        ? recentPosts.filter((p) => p.category === categoria)
        : recentPosts;

    return (
        <>
            <BlogJsonLd />

            {/* Page header: h1 único de la página */}
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
                <BlogFeaturedHero post={featuredPost} />
                <BlogGrid
                    posts={filteredPosts}
                    categories={categories}
                    activeCategory={categoria}
                />
            </main>
        </>
    );
}
