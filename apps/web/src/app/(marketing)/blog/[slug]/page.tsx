import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getBlogPostBySlug, getRelatedPosts, getAllPublishedSlugs } from '../_api';
import type { BlogPostDetail } from '../_api';
import { BlogPostHero } from './_components/BlogPostHero';
import { ShareSidebar } from './_components/ShareSidebar';
import { BlogPostContent } from './_components/BlogPostContent';
import { RelatedPosts } from './_components/RelatedPosts';

const SITE_URL = 'https://www.mirubro.com';

interface BlogPostPageProps {
    params: Promise<{ slug: string }>;
}

export async function generateStaticParams() {
    const slugs = await getAllPublishedSlugs();
    return slugs.map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: BlogPostPageProps): Promise<Metadata> {
    const { slug } = await params;
    const post = await getBlogPostBySlug(slug);

    if (!post) {
        return { title: 'Artículo no encontrado | Mirubro' };
    }

    const url = `${SITE_URL}/blog/${post.slug}`;
    const title = post.metaTitle ?? post.title;
    const description = post.metaDescription ?? post.excerpt;
    const ogImage = post.ogImageUrl
        ? post.ogImageUrl.startsWith('/')
            ? `${SITE_URL}${post.ogImageUrl}`
            : post.ogImageUrl
        : post.coverImageUrl.startsWith('/')
            ? `${SITE_URL}${post.coverImageUrl}`
            : post.coverImageUrl;

    return {
        title: `${title} | Mirubro`,
        description,
        alternates: { canonical: post.canonicalUrl || url },
        openGraph: {
            title: post.ogTitle ?? title,
            description: post.ogDescription ?? description,
            url,
            siteName: 'Mirubro',
            type: 'article',
            publishedTime: post.date,
            authors: ['Mirubro'],
            images: ogImage
                ? [{ url: ogImage, width: 900, alt: post.title }]
                : undefined,
            locale: 'es_AR',
        },
        twitter: {
            card: 'summary_large_image',
            title: post.ogTitle ?? title,
            description: post.ogDescription ?? description,
            images: ogImage ? [ogImage] : undefined,
        },
    };
}

/** JSON-LD: BlogPosting */
function BlogPostingJsonLd({ post }: { post: BlogPostDetail }) {
    const ogImage = post.ogImageUrl
        ? post.ogImageUrl.startsWith('/')
            ? `${SITE_URL}${post.ogImageUrl}`
            : post.ogImageUrl
        : post.coverImageUrl.startsWith('/')
            ? `${SITE_URL}${post.coverImageUrl}`
            : post.coverImageUrl;

    const schema = {
        '@context': 'https://schema.org',
        '@type': 'BlogPosting',
        headline: post.title,
        description: post.metaDescription ?? post.excerpt,
        image: ogImage,
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

export default async function BlogPostPage({ params }: BlogPostPageProps) {
    const { slug } = await params;
    const post = await getBlogPostBySlug(slug);

    if (!post) {
        notFound();
    }

    const formattedDate = dateFormatter.format(new Date(post.date));
    const related = await getRelatedPosts(post);

    return (
        <>
            <BlogPostingJsonLd post={post} />

            <main id="main-content">
                <article>
                    <BlogPostHero post={post} formattedDate={formattedDate} />

                    <div className="mx-auto max-w-4xl px-6 py-10 lg:px-10">
                        <div className="flex gap-10">
                            <ShareSidebar title={post.title} variant="desktop" />
                            <BlogPostContent
                                excerpt={post.excerpt}
                                bodyContent={post.bodyContent}
                            />
                        </div>
                    </div>
                </article>

                <RelatedPosts posts={related} />
            </main>
        </>
    );
}
