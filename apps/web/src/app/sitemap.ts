import type { MetadataRoute } from 'next';
import { getBlogSitemapEntries } from './(marketing)/blog/_api';

const SITE_URL = 'https://www.mirubro.com';

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
    const blogEntries = await getBlogSitemapEntries();

    const staticRoutes: MetadataRoute.Sitemap = [
        { url: SITE_URL, lastModified: new Date(), changeFrequency: 'weekly', priority: 1.0 },
        { url: `${SITE_URL}/blog`, lastModified: new Date(), changeFrequency: 'daily', priority: 0.9 },
        { url: `${SITE_URL}/nosotros`, changeFrequency: 'monthly', priority: 0.5 },
        { url: `${SITE_URL}/preguntas-frecuentes`, changeFrequency: 'monthly', priority: 0.5 },
        { url: `${SITE_URL}/privacidad`, changeFrequency: 'yearly', priority: 0.3 },
        { url: `${SITE_URL}/terminos`, changeFrequency: 'yearly', priority: 0.3 },
    ];

    const blogRoutes: MetadataRoute.Sitemap = blogEntries.map((entry) => ({
        url: `${SITE_URL}/blog/${entry.slug}`,
        lastModified: entry.lastmod ? new Date(entry.lastmod) : new Date(),
        changeFrequency: 'weekly' as const,
        priority: 0.7,
    }));

    return [...staticRoutes, ...blogRoutes];
}
