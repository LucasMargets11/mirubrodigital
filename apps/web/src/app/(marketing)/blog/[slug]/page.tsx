import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getPostBySlug, getRelatedPosts, mockBodyParagraphs, allPosts } from '../_data';
import { BlogPostHero } from './_components/BlogPostHero';
import { ShareSidebar } from './_components/ShareSidebar';
import { BlogPostContent } from './_components/BlogPostContent';
import { RelatedPosts } from './_components/RelatedPosts';

const SITE_URL = 'https://www.mirubro.com';

interface BlogPostPageProps {
    params: Promise<{ slug: string }>;
}

export async function generateStaticParams() {
    return allPosts.map((post) => ({ slug: post.slug }));
}

export async function generateMetadata({ params }: BlogPostPageProps): Promise<Metadata> {
    const { slug } = await params;
    const post = getPostBySlug(slug);

    if (!post) {
        return { title: 'Artículo no encontrado | Mirubro' };
    }

    const url = `${SITE_URL}/blog/${post.slug}`;

    return {
        title: `${post.title} | Mirubro`,
        description: post.excerpt,
        alternates: { canonical: url },
        openGraph: {
            title: post.title,
            description: post.excerpt,
            url,
            siteName: 'Mirubro',
            type: 'article',
            publishedTime: post.date,
            authors: ['Mirubro'],
            images: [
                {
                    url: post.coverImageUrl,
                    width: 900,
                    alt: post.title,
                },
            ],
            locale: 'es_AR',
        },
        twitter: {
            card: 'summary_large_image',
            title: post.title,
            description: post.excerpt,
            images: [post.coverImageUrl],
        },
    };
}

/** JSON-LD: BlogPosting */
function BlogPostingJsonLd({ post }: { post: NonNullable<ReturnType<typeof getPostBySlug>> }) {
    const schema = {
        '@context': 'https://schema.org',
        '@type': 'BlogPosting',
        headline: post.title,
        description: post.excerpt,
        image: post.coverImageUrl,
        url: `${SITE_URL}/blog/${post.slug}`,
        datePublished: post.date,
        dateModified: post.date,
        author: { '@type': 'Organization', name: 'Mirubro', url: SITE_URL },
        publisher: {
            '@type': 'Organization',
            name: 'Mirubro',
            url: SITE_URL,
            logo: { '@type': 'ImageObject', url: `${SITE_URL}/logo/rubroicono.png` },
        },
        mainEntityOfPage: { '@type': 'WebPage', '@id': `${SITE_URL}/blog/${post.slug}` },
    };
    return (
        <script
            type="application/ld+json"
            dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
        />
    );
}

const dateFormatter = new Intl.DateTimeFormat('es', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
});

/**
 * Página detalle de un post: /blog/:slug
 *
 * Estructura semántica:
 *   main > article
 *     BlogPostHero      (breadcrumb + meta + h1 + cover)
 *     ── 2 cols desktop: ShareSidebar sticky | BlogPostContent ──
 *   RelatedPosts        (sección propia, fuera del article)
 */
export default async function BlogPostPage({ params }: BlogPostPageProps) {
    const { slug } = await params;
    const post = getPostBySlug(slug);

    if (!post) {
        notFound();
    }

    const formattedDate = dateFormatter.format(new Date(post.date));
    const related = getRelatedPosts(post);

    return (
        <>
            <BlogPostingJsonLd post={post} />

            <main id="main-content">
                <article>
                    {/* Hero: breadcrumb + meta + h1 + cover */}
                    <BlogPostHero post={post} formattedDate={formattedDate} />

                    {/* Body: 2-column layout on desktop */}
                    <div className="mx-auto max-w-4xl px-6 py-10 lg:px-10">
                        <div className="flex gap-10">
                            {/* Sticky sidebar — desktop only */}
                            <ShareSidebar title={post.title} variant="desktop" />

                            {/* Editorial content */}
                            <BlogPostContent
                                excerpt={post.excerpt}
                                paragraphs={mockBodyParagraphs}
                            />
                        </div>
                    </div>
                </article>

                {/* Related posts — outside article */}
                <RelatedPosts posts={related} />
            </main>
        </>
    );
}
