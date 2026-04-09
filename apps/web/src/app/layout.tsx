import type { Metadata } from 'next';
import { Inter, Space_Grotesk } from 'next/font/google';
import '../styles/globals.css';
import { ConsentProvider } from '@/lib/consent/ConsentProvider';
import { CookieBanner } from '@/components/consent/CookieBanner';

const inter = Inter({
    subsets: ['latin'],
    weight: ['400', '500', '600'],
    variable: '--font-inter',
    display: 'swap',
});

const spaceGrotesk = Space_Grotesk({
    subsets: ['latin'],
    weight: ['500', '600'],
    variable: '--font-space-grotesk',
    display: 'swap',
});

export const metadata: Metadata = {
    metadataBase: new URL('https://www.mirubro.com'),
    title: 'Mirubro',
    description: 'Plataforma de gestión para gastronomía.',
    icons: {
        icon: [
            { url: '/favicon.ico', sizes: '48x48' },
            { url: '/logo/rubroicono.png', type: 'image/png' },
        ],
        apple: '/apple-touch-icon.png',
    },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="es" className={`h-full ${inter.variable} ${spaceGrotesk.variable}`}>
            <body className="h-full font-sans">
                <ConsentProvider>
                    {children}
                    <CookieBanner />
                </ConsentProvider>
            </body>
        </html>
    );
}
