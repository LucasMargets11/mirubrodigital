import { ImageResponse } from 'next/og';

export const alt = 'Mirubro — Software de gestión para comercios y gastronomía';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function OgImage() {
    return new ImageResponse(
        (
            <div
                style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '100%',
                    height: '100%',
                    background: 'linear-gradient(145deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)',
                    fontFamily: 'sans-serif',
                }}
            >
                {/* Brand mark */}
                <div
                    style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        gap: '28px',
                    }}
                >
                    {/* Logo circle */}
                    <div
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            width: '80px',
                            height: '80px',
                            borderRadius: '20px',
                            background: 'linear-gradient(135deg, #3b82f6, #2563eb)',
                        }}
                    >
                        <span style={{ fontSize: '40px', fontWeight: 800, color: '#ffffff' }}>M</span>
                    </div>

                    {/* Title */}
                    <span
                        style={{
                            fontSize: '64px',
                            fontWeight: 700,
                            color: '#ffffff',
                            letterSpacing: '-2px',
                        }}
                    >
                        Mirubro
                    </span>

                    {/* Tagline */}
                    <span
                        style={{
                            fontSize: '26px',
                            color: '#94a3b8',
                            maxWidth: '700px',
                            textAlign: 'center',
                            lineHeight: 1.4,
                        }}
                    >
                        Software de gestión para comercios y gastronomía
                    </span>

                    {/* Domain */}
                    <span
                        style={{
                            fontSize: '18px',
                            color: '#64748b',
                            marginTop: '8px',
                        }}
                    >
                        www.mirubro.com
                    </span>
                </div>
            </div>
        ),
        { ...size }
    );
}
