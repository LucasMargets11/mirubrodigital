import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getBlogPostPreview } from '../../_api';
import { BlogPostHero } from '../../[slug]/_components/BlogPostHero';
import { ShareSidebar } from '../../[slug]/_components/ShareSidebar';
import { BlogPostContent } from '../../[slug]/_components/BlogPostContent';

export const metadata: Metadata = {
    title: 'Preview | Mirubro Blog',
    robots: { index: false, follow: false },
};

interface PreviewPageProps {
    params: Promise<{ postId: string }>;
    searchParams: Promise<{ token?: string; ts?: string }>;
}

const STATUS_LABELS: Record<string, string> = {
    draft: 'Borrador',
    scheduled: 'Programado',
    published: 'Publicado',
    archived: 'Archivado',
};

export default async function BlogPreviewPage({ params, searchParams }: PreviewPageProps) {
    const { postId } = await params;
    const { token, ts } = await searchParams;

    if (!token || !ts) {
        notFound();
    }

    const post = await getBlogPostPreview(postId, token, ts);

    if (!post) {
        notFound();
    }

    const dateFormatter = new Intl.DateTimeFormat('es', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
    });
    const formattedDate = post.date
        ? dateFormatter.format(new Date(post.date))
        : 'Sin fecha';

    const statusLabel = post.status ? STATUS_LABELS[post.status] ?? post.status : '';

    return (
        <>
            {/* Preview banner — noindex already in metadata */}
            <div className="sticky top-0 z-50 border-b border-amber-300 bg-amber-50 px-4 py-2 text-center text-sm font-medium text-amber-800">
                Vista previa editorial
                {statusLabel && (
                    <span className="ml-2 rounded bg-amber-200 px-2 py-0.5 text-xs font-semibold uppercase">
                        {statusLabel}
                    </span>
                )}
                <span className="ml-2 text-amber-600">— Este contenido no es público.</span>
            </div>

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
            </main>
        </>
    );
}
