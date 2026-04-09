import type { MetadataRoute } from 'next';

export default function robots(): MetadataRoute.Robots {
    return {
        rules: [
            {
                userAgent: '*',
                allow: '/',
                disallow: ['/app/', '/admin/', '/pos/', '/q/', '/m/', '/r/', '/subscribe/'],
            },
        ],
        sitemap: 'https://www.mirubro.com/sitemap.xml',
    };
}
