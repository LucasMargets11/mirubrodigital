"use client";

import { useEffect } from "react";
import { MenuCategory, MenuConfig } from "./types";
import { MenuCategorySection } from "./category-section";
import { MenuBrandHeader } from "./brand-header";
import { getMenuFontFamily } from "@/lib/fonts";

interface PublicMenuLayoutProps {
    config: MenuConfig;
    categories: MenuCategory[];
}

export function PublicMenuLayout({ config, categories }: PublicMenuLayoutProps) {
    const theme = config.theme_json || {};
    
    // Construct CSS variables
    const styles = {
        '--menu-bg': theme.background || '#0a0a0a',
        '--menu-text': theme.text || '#ffffff',
        '--menu-muted': theme.mutedText || '#a3a3a3',
        '--menu-accent': theme.accent || '#8b5cf6',
        '--menu-divider': theme.divider || '#262626',
        '--menu-font-body': getMenuFontFamily(theme.bodyFont || theme.fontFamily),
        '--menu-font-heading': getMenuFontFamily(theme.headingFont || theme.bodyFont || theme.fontFamily),
        '--menu-size-heading': `${theme.menuHeadingFontSize || 1.25}rem`,
        '--menu-size-body': `${theme.menuBodyFontSize || 1}rem`,
    } as React.CSSProperties;

    // Ensure body background matches theme (avoid white flickering or overscroll issues)
    // Also override global height:100% on html/body to allow full expansion
    useEffect(() => {
        const bg = theme.background || '#0a0a0a';
        
        const prevHtmlBg = document.documentElement.style.backgroundColor;
        const prevBodyBg = document.body.style.backgroundColor;
        const prevBodyBgImage = document.body.style.backgroundImage;
        const prevBodyHeight = document.body.style.height;

        document.documentElement.style.backgroundColor = bg;
        document.body.style.backgroundColor = bg;
        document.body.style.backgroundImage = 'none';
        // Override global height: 100% to allow body to grow with content
        document.body.style.height = 'auto';
        document.body.style.minHeight = '100vh';

        return () => {
            document.documentElement.style.backgroundColor = prevHtmlBg;
            document.body.style.backgroundColor = prevBodyBg;
            document.body.style.backgroundImage = prevBodyBgImage;
            document.body.style.height = prevBodyHeight;
            document.body.style.minHeight = '';
        };
    }, [theme.background]);

    return (
        <main 
            style={styles} 
            className="relative flex-1 w-full bg-[var(--menu-bg)] text-[var(--menu-text)] font-[family-name:var(--menu-font-body)] selection:bg-[var(--menu-accent)] selection:text-[var(--menu-bg)] overflow-hidden"
        >
             {/* Watermark Background */}
             {theme.menuLogoUrl && theme.menuLogoPosition === 'watermark' && (
                <div 
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-0 z-0 flex items-center justify-center p-12"
                    style={{ opacity: theme.menuLogoWatermarkOpacity || 0.08 }}
                >
                     <img 
                        src={theme.menuLogoUrl} 
                        alt="" 
                        className="w-full max-w-3xl object-contain opacity-100 grayscale transition-all duration-300"
                        style={{ filter: 'grayscale(100%)' }} // Optional: make watermark B&W? User didn't specify, but "watermark" implies subtle.
                     />
                </div>
            )}

            <div className="relative z-10 w-full px-6 py-10 lg:px-12 2xl:px-16">
                
                {/* Header */}
                <MenuBrandHeader 
                    brandDetails={{ name: config.brand_name, description: config.description }}
                    theme={theme}
                />

                {/* Columns Container */}
                <div className="columns-1 gap-12 text-sm [column-fill:balance] lg:columns-2 2xl:columns-3">
                    {categories.map((category) => (
                        <MenuCategorySection key={category.id} category={category} />
                    ))}
                </div>

                {/* Footer */}
                <div className="mt-20 border-t border-[var(--menu-divider)] pt-8 text-center text-xs text-[var(--menu-muted)] opacity-60">
                    <p>Precios e impuestos sujetos a cambios sin previo aviso.</p>
                    <p className="mt-1">© {new Date().getFullYear()} {config.brand_name} — Powered by Mirubro</p>
                </div>
            </div>
        </main>
    );
}
