import { ImageResponse } from 'next/og';
import { getBlogPostBySlug } from '../_api';

export const alt = 'Mirubro Blog';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default async function OgImage({ params }: { params: Promise<{ slug: string }> }) {
    const { slug } = await params;
    const post = await getBlogPostBySlug(slug);

    const title = post?.title ?? 'Artículo de Mirubro';
    const category = post?.category ?? '';

    return new ImageResponse(
        (
            <div
                style={{
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    width: '100%',
                    height: '100%',
                    background: 'linear-gradient(145deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)',
                    fontFamily: 'sans-serif',
                    padding: '60px',
                }}
            >
                {/* Top: category + brand */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    {category ? (
                        <span
                            style={{
                                fontSize: '16px',
                                fontWeight: 600,
                                color: '#94a3b8',
                                textTransform: 'uppercase',
                                letterSpacing: '2px',
                            }}
                        >
                            {category}
                        </span>
                    ) : (
                        <span />
                    )}
                    <span style={{ fontSize: '20px', fontWeight: 700, color: '#3b82f6' }}>
                        Mirubro
                    </span>
                </div>

                {/* Center: title */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <span
                        style={{
                            fontSize: title.length > 60 ? '40px' : '52px',
                            fontWeight: 700,
                            color: '#ffffff',
                            lineHeight: 1.2,
                            maxWidth: '900px',
                        }}
                    >
                        {title}
                    </span>
                </div>

                {/* Bottom: domain */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span style={{ fontSize: '16px', color: '#64748b' }}>www.mirubro.com/blog</span>
                </div>
            </div>
        ),
        { ...size }
    );
}
