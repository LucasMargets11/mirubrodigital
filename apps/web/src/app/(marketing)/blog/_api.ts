/**
 * Blog CMS data adapter — server-side only.
 *
 * This module fetches published posts from the real CMS API and maps them
 * to the same BlogPost / BlogCategory interfaces used by all frontend
 * components.  It replaces the static _data.ts as the authoritative
 * source of truth.
 *
 * ⚠  Import this ONLY from Server Components / generateMetadata / generateStaticParams.
 *    Do NOT use in client components (it calls serverApiFetch which relies on next/headers).
 */
import { serverApiFetch } from '@/lib/api/server';
import type { BlogPost, BlogCategory, ContentBlock } from './_types';

// ── API response types ───────────────────────────────────────────────────────

interface ApiPostSummary {
    slug: string;
    title: string;
    excerpt: string;
    cover_image_url: string;
    reading_time: string;
    date: string;
    source_label: string;
    category_slug: string | null;
    category_label: string | null;
    author_name: string | null;
    meta_title: string;
    meta_description: string;
}

interface ApiPostDetail extends ApiPostSummary {
    body_content: ContentBlock[];
    tags: string[];
    og_title: string;
    og_description: string;
    og_image_url: string;
    canonical_url: string;
    // preview-only fields
    is_preview?: boolean;
    status?: string;
}

interface ApiPostList {
    results: ApiPostSummary[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
}

interface ApiCategoryList {
    results: Array<{ slug: string; label: string }>;
}

interface ApiSitemapResponse {
    posts: Array<{ slug: string; published_at: string | null }>;
}

// ── Mappers: API shape → frontend BlogPost shape ─────────────────────────────

function mapSummaryToPost(raw: ApiPostSummary): BlogPost {
    return {
        slug: raw.slug,
        title: raw.title,
        excerpt: raw.excerpt,
        coverImageUrl: raw.cover_image_url || '',
        readingTime: raw.reading_time || '',
        date: raw.date ? raw.date.split('T')[0]! : '',
        sourceLabel: raw.source_label || 'MIRUBRO',
        category: raw.category_slug || '',
        metaTitle: raw.meta_title || undefined,
        metaDescription: raw.meta_description || undefined,
    };
}

function mapDetailToPost(raw: ApiPostDetail): BlogPost {
    return {
        ...mapSummaryToPost(raw),
        bodyContent: raw.body_content?.length ? raw.body_content : undefined,
        // Extra fields carried via the same interface so pages can use them
        metaTitle: raw.meta_title || raw.title,
        metaDescription: raw.meta_description || raw.excerpt,
    };
}

/** Extended detail beyond the public BlogPost interface — passed to SEO helpers. */
export interface BlogPostDetail extends BlogPost {
    ogTitle: string;
    ogDescription: string;
    ogImageUrl: string;
    canonicalUrl: string;
    isPreview?: boolean;
    status?: string;
}

function mapDetailToFull(raw: ApiPostDetail): BlogPostDetail {
    return {
        ...mapDetailToPost(raw),
        ogTitle: raw.og_title || raw.meta_title || raw.title,
        ogDescription: raw.og_description || raw.meta_description || raw.excerpt,
        ogImageUrl: raw.og_image_url || raw.cover_image_url || '',
        canonicalUrl: raw.canonical_url || '',
        isPreview: raw.is_preview,
        status: raw.status,
    };
}

// ── Public data functions (server-side) ──────────────────────────────────────

/**
 * Fetch published posts for the /blog listing.
 * Returns { posts, categories, featured, total, page, totalPages }.
 */
export async function getBlogListing(opts?: {
    category?: string;
    page?: number;
}): Promise<{
    posts: BlogPost[];
    total: number;
    page: number;
    totalPages: number;
}> {
    const params = new URLSearchParams();
    if (opts?.category) params.set('category', opts.category);
    if (opts?.page && opts.page > 1) params.set('page', String(opts.page));

    try {
        const data = await serverApiFetch<ApiPostList>(
            `/api/v1/blog/posts/?${params.toString()}`
        );
        return {
            posts: data.results.map(mapSummaryToPost),
            total: data.total,
            page: data.page,
            totalPages: data.total_pages,
        };
    } catch {
        return { posts: [], total: 0, page: 1, totalPages: 1 };
    }
}

/**
 * Fetch a single published post by slug for /blog/[slug].
 * Returns null if not found or not published.
 */
export async function getBlogPostBySlug(slug: string): Promise<BlogPostDetail | null> {
    try {
        const raw = await serverApiFetch<ApiPostDetail>(
            `/api/v1/blog/posts/${encodeURIComponent(slug)}/`
        );
        return mapDetailToFull(raw);
    } catch {
        return null;
    }
}

/**
 * Fetch a post via the preview endpoint (token-protected, any status).
 */
export async function getBlogPostPreview(
    postId: string,
    token: string,
    ts: string
): Promise<BlogPostDetail | null> {
    try {
        const raw = await serverApiFetch<ApiPostDetail>(
            `/api/v1/blog/preview/${encodeURIComponent(postId)}/?token=${encodeURIComponent(token)}&ts=${encodeURIComponent(ts)}`
        );
        return mapDetailToFull(raw);
    } catch {
        return null;
    }
}

/**
 * Fetch categories that have at least one published post.
 */
export async function getBlogCategories(): Promise<BlogCategory[]> {
    try {
        const data = await serverApiFetch<ApiCategoryList>('/api/v1/blog/categories/');
        return data.results;
    } catch {
        return [];
    }
}

/**
 * Fetch related posts for a given post (same category first, then recent).
 * Uses the listing endpoint filtered by category, excluding the current slug.
 */
export async function getRelatedPosts(
    current: BlogPost,
    limit = 3
): Promise<BlogPost[]> {
    try {
        const params = new URLSearchParams();
        if (current.category) params.set('category', current.category);

        const data = await serverApiFetch<ApiPostList>(
            `/api/v1/blog/posts/?${params.toString()}`
        );
        const others = data.results
            .filter((p) => p.slug !== current.slug)
            .map(mapSummaryToPost);

        if (others.length >= limit) return others.slice(0, limit);

        // Fallback: fetch recent posts without category filter
        const fallback = await serverApiFetch<ApiPostList>('/api/v1/blog/posts/');
        const extra = fallback.results
            .filter((p) => p.slug !== current.slug && !others.some((o) => o.slug === p.slug))
            .map(mapSummaryToPost);

        return [...others, ...extra].slice(0, limit);
    } catch {
        return [];
    }
}

/**
 * Fetch all published post slugs (for generateStaticParams / sitemap).
 */
export async function getAllPublishedSlugs(): Promise<string[]> {
    try {
        const data = await serverApiFetch<ApiSitemapResponse>('/api/v1/blog/sitemap/');
        return data.posts.map((p) => p.slug);
    } catch {
        return [];
    }
}

/**
 * Fetch sitemap entries for blog posts.
 */
export async function getBlogSitemapEntries(): Promise<
    Array<{ slug: string; lastmod: string }>
> {
    try {
        const data = await serverApiFetch<ApiSitemapResponse>('/api/v1/blog/sitemap/');
        return data.posts.map((p) => ({
            slug: p.slug,
            lastmod: p.published_at ?? new Date().toISOString(),
        }));
    } catch {
        return [];
    }
}

// ── ISR-safe public fetchers (no cookies → no forced dynamic) ────────────────
//
// These use plain fetch() with next.revalidate instead of serverApiFetch
// (which calls cookies() and opts the route into dynamic rendering).
// Safe to use from static/ISR pages like the marketing home.

const BLOG_REVALIDATE_SECONDS = 3600; // 1 hour

function getInternalApiUrl(): string {
    return (
        process.env.API_INTERNAL_URL ??
        process.env.INTERNAL_API_URL ??
        process.env.NEXT_PUBLIC_API_URL ??
        'http://localhost:8000'
    );
}

/**
 * Fetch blog listing without auth — ISR-safe (no cookies).
 * Used by BlogResourcesSection on the home page and /blog listing.
 */
export async function getBlogListingCached(opts?: {
    category?: string;
    page?: number;
}): Promise<{
    posts: BlogPost[];
    total: number;
    page: number;
    totalPages: number;
}> {
    const params = new URLSearchParams();
    if (opts?.category) params.set('category', opts.category);
    if (opts?.page && opts.page > 1) params.set('page', String(opts.page));

    try {
        const res = await fetch(
            `${getInternalApiUrl()}/api/v1/blog/posts/?${params.toString()}`,
            {
                headers: { 'Content-Type': 'application/json' },
                next: { revalidate: BLOG_REVALIDATE_SECONDS },
            }
        );
        if (!res.ok) throw new Error(`API ${res.status}`);
        const data: ApiPostList = await res.json();
        return {
            posts: data.results.map(mapSummaryToPost),
            total: data.total,
            page: data.page,
            totalPages: data.total_pages,
        };
    } catch {
        return { posts: [], total: 0, page: 1, totalPages: 1 };
    }
}

/**
 * Fetch blog categories without auth — ISR-safe (no cookies).
 */
export async function getBlogCategoriesCached(): Promise<BlogCategory[]> {
    try {
        const res = await fetch(
            `${getInternalApiUrl()}/api/v1/blog/categories/`,
            {
                headers: { 'Content-Type': 'application/json' },
                next: { revalidate: BLOG_REVALIDATE_SECONDS },
            }
        );
        if (!res.ok) throw new Error(`API ${res.status}`);
        const data: ApiCategoryList = await res.json();
        return data.results;
    } catch {
        return [];
    }
}
