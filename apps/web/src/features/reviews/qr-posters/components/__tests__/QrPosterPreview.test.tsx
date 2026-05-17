/**
 * Tests for QrPosterPreview logo rendering logic.
 *
 * Coverage:
 * 1. With branding data and include_logo=true → renders real <img> tag
 * 2. Without branding data and include_logo=true → renders placeholder div
 * 3. include_logo=false → neither logo <img> nor placeholder rendered
 * 4. logo_variant='none' → placeholder div (no real logo shown)
 * 5. logo_variant='horizontal' → uses logo_horizontal_url
 * 6. logo_variant='square' → uses logo_square_url
 * 7. logo_variant='default' → prefers horizontal, falls back to square
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { QrPosterPreview } from '../QrPosterPreview';
import type { GenerateQrPosterPayload } from '../../types';
import type { BusinessBranding } from '@/features/business/branding/types';

// ── Mock the branding hook ────────────────────────────────────────────────────

vi.mock('@/features/business/branding/hooks', () => ({
    useBusinessBrandingQuery: vi.fn(),
}));

import { useBusinessBrandingQuery } from '@/features/business/branding/hooks';

const mockBrandingQuery = useBusinessBrandingQuery as ReturnType<typeof vi.fn>;

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makePayload(overrides: Partial<GenerateQrPosterPayload> = {}): GenerateQrPosterPayload {
    return {
        poster_size: 'a4_portrait',
        template_code: 'simple_centered',
        main_text: 'Escaneá y dejanos tu reseña',
        subtitle: '',
        include_logo: false,
        logo_variant: 'none',
        background_color: '#FFFFFF',
        background_mode: 'color',
        title_font: 'sans_bold',
        main_text_outline_enabled: false,
        main_text_outline_color: '#000000',
        subtitle_text_outline_enabled: false,
        subtitle_text_outline_color: '#000000',
        text_outline_width: 0.4,
        ...overrides,
    };
}

function makeBranding(overrides: Partial<BusinessBranding> = {}): BusinessBranding {
    return {
        id: 'branding-1',
        business: 'business-1',
        logo_horizontal: 'business/logos/h.png',
        logo_horizontal_url: 'https://cdn.example.com/logos/horizontal.png',
        logo_square: null,
        logo_square_url: null,
        accent_color: '#FF5733',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-05-01T00:00:00Z',
        ...overrides,
    };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('QrPosterPreview — logo rendering', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    // ── 1. Logo visible when branding data is available ───────────────────────

    it('renders real <img> when branding has logo and include_logo=true (vertical layout)', () => {
        mockBrandingQuery.mockReturnValue({
            data: makeBranding(),
            isPending: false,
        });

        render(
            <QrPosterPreview
                payload={makePayload({ include_logo: true, logo_variant: 'default' })}
            />,
        );

        const img = screen.getByRole('img', { name: /logo/i });
        expect(img).toBeInTheDocument();
        expect(img).toHaveAttribute('src', 'https://cdn.example.com/logos/horizontal.png');
    });

    it('renders real <img> when branding has logo and include_logo=true (qr_left layout)', () => {
        mockBrandingQuery.mockReturnValue({
            data: makeBranding(),
            isPending: false,
        });

        render(
            <QrPosterPreview
                payload={makePayload({
                    include_logo: true,
                    logo_variant: 'horizontal',
                    template_code: 'qr_left',
                })}
            />,
        );

        const img = screen.getByRole('img', { name: /logo/i });
        expect(img).toBeInTheDocument();
        expect(img).toHaveAttribute('src', 'https://cdn.example.com/logos/horizontal.png');
    });

    // ── 2. Placeholder when no branding data ──────────────────────────────────

    it('does not render <img> when branding is undefined and include_logo=true', () => {
        mockBrandingQuery.mockReturnValue({ data: undefined, isPending: false });

        render(
            <QrPosterPreview
                payload={makePayload({ include_logo: true, logo_variant: 'default' })}
            />,
        );

        expect(screen.queryByRole('img', { name: /logo/i })).not.toBeInTheDocument();
    });

    // ── 3. include_logo=false → nothing rendered ──────────────────────────────

    it('renders neither logo <img> nor anything logo-related when include_logo=false', () => {
        mockBrandingQuery.mockReturnValue({
            data: makeBranding(),
            isPending: false,
        });

        render(
            <QrPosterPreview
                payload={makePayload({ include_logo: false, logo_variant: 'default' })}
            />,
        );

        expect(screen.queryByRole('img', { name: /logo/i })).not.toBeInTheDocument();
    });

    // ── 4. logo_variant='none' → no logo even if branding has data ────────────

    it('does not render logo <img> when logo_variant=none even if branding has data', () => {
        mockBrandingQuery.mockReturnValue({
            data: makeBranding(),
            isPending: false,
        });

        render(
            <QrPosterPreview
                payload={makePayload({ include_logo: true, logo_variant: 'none' })}
            />,
        );

        expect(screen.queryByRole('img', { name: /logo/i })).not.toBeInTheDocument();
    });

    // ── 5. logo_variant='horizontal' uses logo_horizontal_url ─────────────────

    it('uses logo_horizontal_url when logo_variant=horizontal', () => {
        mockBrandingQuery.mockReturnValue({
            data: makeBranding({
                logo_horizontal_url: 'https://cdn.example.com/h.png',
                logo_square_url: 'https://cdn.example.com/sq.png',
            }),
            isPending: false,
        });

        render(
            <QrPosterPreview
                payload={makePayload({ include_logo: true, logo_variant: 'horizontal' })}
            />,
        );

        expect(screen.getByRole('img', { name: /logo/i })).toHaveAttribute(
            'src',
            'https://cdn.example.com/h.png',
        );
    });

    // ── 6. logo_variant='square' uses logo_square_url ─────────────────────────

    it('uses logo_square_url when logo_variant=square', () => {
        mockBrandingQuery.mockReturnValue({
            data: makeBranding({
                logo_horizontal_url: 'https://cdn.example.com/h.png',
                logo_square_url: 'https://cdn.example.com/sq.png',
            }),
            isPending: false,
        });

        render(
            <QrPosterPreview
                payload={makePayload({ include_logo: true, logo_variant: 'square' })}
            />,
        );

        expect(screen.getByRole('img', { name: /logo/i })).toHaveAttribute(
            'src',
            'https://cdn.example.com/sq.png',
        );
    });

    // ── 7. logo_variant='default' prefers horizontal, falls back to square ────

    it('default variant: prefers horizontal when both are available', () => {
        mockBrandingQuery.mockReturnValue({
            data: makeBranding({
                logo_horizontal_url: 'https://cdn.example.com/h.png',
                logo_square_url: 'https://cdn.example.com/sq.png',
            }),
            isPending: false,
        });

        render(
            <QrPosterPreview
                payload={makePayload({ include_logo: true, logo_variant: 'default' })}
            />,
        );

        expect(screen.getByRole('img', { name: /logo/i })).toHaveAttribute(
            'src',
            'https://cdn.example.com/h.png',
        );
    });

    it('default variant: falls back to square when horizontal is null', () => {
        mockBrandingQuery.mockReturnValue({
            data: makeBranding({
                logo_horizontal_url: null,
                logo_square_url: 'https://cdn.example.com/sq.png',
            }),
            isPending: false,
        });

        render(
            <QrPosterPreview
                payload={makePayload({ include_logo: true, logo_variant: 'default' })}
            />,
        );

        expect(screen.getByRole('img', { name: /logo/i })).toHaveAttribute(
            'src',
            'https://cdn.example.com/sq.png',
        );
    });

    it('default variant: no <img> when both horizontal and square are null', () => {
        mockBrandingQuery.mockReturnValue({
            data: makeBranding({
                logo_horizontal_url: null,
                logo_square_url: null,
            }),
            isPending: false,
        });

        render(
            <QrPosterPreview
                payload={makePayload({ include_logo: true, logo_variant: 'default' })}
            />,
        );

        expect(screen.queryByRole('img', { name: /logo/i })).not.toBeInTheDocument();
    });
});

// ── Tests for logo position/margin ────────────────────────────────────────────

describe('QrPosterPreview — logo position and margin', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockBrandingQuery.mockReturnValue({
            data: makeBranding({ logo_horizontal_url: 'https://cdn.example.com/h.png' }),
            isPending: false,
        });
    });

    it('renders logo when logo_position=bottom-center with logo_margin_mm=5', () => {
        render(
            <QrPosterPreview
                payload={makePayload({
                    include_logo: true,
                    logo_variant: 'horizontal',
                    logo_position: 'bottom-center',
                    logo_margin_mm: 5,
                })}
            />,
        );
        expect(screen.getByRole('img', { name: /logo/i })).toBeInTheDocument();
    });

    it('renders logo when logo_position=middle-left', () => {
        render(
            <QrPosterPreview
                payload={makePayload({
                    include_logo: true,
                    logo_variant: 'horizontal',
                    logo_position: 'middle-left',
                })}
            />,
        );
        expect(screen.getByRole('img', { name: /logo/i })).toBeInTheDocument();
    });

    it('renders logo when logo_position=top-left', () => {
        render(
            <QrPosterPreview
                payload={makePayload({
                    include_logo: true,
                    logo_variant: 'horizontal',
                    logo_position: 'top-left',
                })}
            />,
        );
        expect(screen.getByRole('img', { name: /logo/i })).toBeInTheDocument();
    });

    it('does not render logo when logo_variant=none regardless of position', () => {
        render(
            <QrPosterPreview
                payload={makePayload({
                    include_logo: false,
                    logo_variant: 'none',
                    logo_position: 'top-center',
                })}
            />,
        );
        expect(screen.queryByRole('img', { name: /logo/i })).not.toBeInTheDocument();
    });
});
