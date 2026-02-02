import { LayoutTheme } from '@/features/menu/types';

export type OnlineMenuPreset = {
    id: string;
    name: string;
    colors: {
        background: string;
        text: string;
        mutedText: string;
        accent: string;
        divider: string;
    };
    fonts: {
        headingFont: string;
        bodyFont: string;
    };
};

export const ONLINE_MENU_PRESETS: OnlineMenuPreset[] = [
    {
        id: 'noir_premium',
        name: 'Noir Premium',
        colors: {
            background: '#0a0a0a',
            text: '#ffffff',
            mutedText: '#a3a3a3',
            accent: '#ffffff',
            divider: '#262626',
        },
        fonts: {
            headingFont: 'playfair_display',
            bodyFont: 'inter',
        },
    },
    {
        id: 'classic_bistro',
        name: 'Classic Bistro',
        colors: {
            background: '#ffffff',
            text: '#0f172a',
            mutedText: '#64748b',
            accent: '#0f172a',
            divider: '#e2e8f0',
        },
        fonts: {
            headingFont: 'playfair_display',
            bodyFont: 'libre_baskerville',
        },
    },
    {
        id: 'minimal_white',
        name: 'Minimal White',
        colors: {
            background: '#ffffff',
            text: '#171717',
            mutedText: '#737373',
            accent: '#171717',
            divider: '#f5f5f5',
        },
        fonts: {
            headingFont: 'inter',
            bodyFont: 'inter',
        },
    },
    {
        id: 'nord_clean',
        name: 'Nord Clean',
        colors: {
            background: '#2e3440',
            text: '#eceff4',
            mutedText: '#d8dee9',
            accent: '#88c0d0',
            divider: '#434c5e',
        },
        fonts: {
            headingFont: 'source_sans_3',
            bodyFont: 'source_sans_3',
        },
    },
    {
        id: 'forest_olive',
        name: 'Forest Olive',
        colors: {
            background: '#1a2e1a',
            text: '#e2e8f0',
            mutedText: '#94a3b8',
            accent: '#a3e635',
            divider: '#2f4f2f',
        },
        fonts: {
            headingFont: 'merriweather',
            bodyFont: 'alegreya_sans',
        },
    },
    {
        id: 'wine_cream',
        name: 'Wine & Cream',
        colors: {
            background: '#fdf4f5',
            text: '#4a0404',
            mutedText: '#7f1d1d',
            accent: '#9f1239',
            divider: '#fecdd3',
        },
        fonts: {
            headingFont: 'lora',
            bodyFont: 'lora',
        },
    },
    {
        id: 'coffee_house',
        name: 'Coffee House',
        colors: {
            background: '#271c19',
            text: '#e6d5c3',
            mutedText: '#a89078',
            accent: '#d4b483',
            divider: '#4e342e',
        },
        fonts: {
            headingFont: 'alegreya',
            bodyFont: 'alegreya_sans',
        },
    },
    {
        id: 'ocean_modern',
        name: 'Ocean Modern',
        colors: {
            background: '#0f172a',
            text: '#f8fafc',
            mutedText: '#94a3b8',
            accent: '#38bdf8',
            divider: '#1e293b',
        },
        fonts: {
            headingFont: 'source_sans_3',
            bodyFont: 'inter',
        },
    },
    {
        id: 'monochrome_editorial',
        name: 'Monochrome Editorial',
        colors: {
            background: '#ffffff',
            text: '#000000',
            mutedText: '#525252',
            accent: '#000000',
            divider: '#e5e5e5',
        },
        fonts: {
            headingFont: 'cormorant_garamond',
            bodyFont: 'source_sans_3',
        },
    },
    {
        id: 'neon_night',
        name: 'Neon Night',
        colors: {
            background: '#09090b',
            text: '#e4e4e7',
            mutedText: '#a1a1aa',
            accent: '#22c55e',
            divider: '#27272a',
        },
        fonts: {
            headingFont: 'source_sans_3',
            bodyFont: 'inter',
        },
    },
];

export function applyPreset(theme: Partial<LayoutTheme>, presetId: string): Partial<LayoutTheme> {
    const preset = ONLINE_MENU_PRESETS.find(p => p.id === presetId);
    if (!preset) return theme;

    return {
        ...theme,
        ...preset.colors,
        headingFont: preset.fonts.headingFont,
        bodyFont: preset.fonts.bodyFont,
        fontFamily: preset.fonts.bodyFont, // Keep for backward compatibility/fallback
    };
}
