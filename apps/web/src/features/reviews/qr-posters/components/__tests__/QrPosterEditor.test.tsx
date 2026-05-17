/**
 * Tests for QrPosterEditor logo section.
 *
 * Coverage:
 * 1. Shows variant selector buttons (Sin logo / Horizontal / Cuadrado)
 * 2. When logo_variant='none': position grid and margin slider not shown
 * 3. When logo_variant='horizontal': position grid and margin slider shown
 * 4. Clicking a variant button calls onChange with correct logo_variant + include_logo
 * 5. Missing logo warning shown when variant has no URL loaded
 * 6. Warning links to /app/resenas/configuracion#marca
 * 7. Warning NOT shown when the chosen variant has a logo URL loaded
 * 8. Margin slider present when logo variant != none
 */

import React from 'react';
import { render, screen, within, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { QrPosterEditor } from '../QrPosterEditor';
import type { GenerateQrPosterPayload } from '../../types';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('../hooks', () => ({
    useGenerateQrPosterPdf: () => ({
        generate: vi.fn(),
        isLoading: false,
        error: null,
        clearError: vi.fn(),
    }),
}));

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

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('QrPosterEditor — logo section', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockBrandingQuery.mockReturnValue({ data: undefined, isPending: false });
    });

    it('shows variant selector buttons', () => {
        const { container } = render(
            <QrPosterEditor
                payload={makePayload()}
                onChange={vi.fn()}
            />,
        );
        // Scope to the logo section (first parent section of "Logo del negocio" label)
        const logoLabel = screen.getByText('Logo del negocio');
        const logoSection = logoLabel.closest('section')!;
        expect(within(logoSection).getByRole('button', { name: /sin logo/i })).toBeInTheDocument();
        expect(within(logoSection).getByRole('button', { name: /horizontal/i })).toBeInTheDocument();
        expect(within(logoSection).getByRole('button', { name: /cuadrado/i })).toBeInTheDocument();
    });

    it('does not show position grid or margin slider when logo_variant=none', () => {
        render(
            <QrPosterEditor
                payload={makePayload({ logo_variant: 'none' })}
                onChange={vi.fn()}
            />,
        );
        const logoSection = screen.getByText('Logo del negocio').closest('section')!;
        expect(within(logoSection).queryByText(/posición/i)).not.toBeInTheDocument();
        expect(within(logoSection).queryByText(/margen del logo/i)).not.toBeInTheDocument();
    });

    it('shows position grid and margin slider when logo_variant=horizontal', () => {
        mockBrandingQuery.mockReturnValue({
            data: { logo_horizontal_url: 'https://cdn.example.com/h.png', logo_square_url: null },
            isPending: false,
        });
        render(
            <QrPosterEditor
                payload={makePayload({ logo_variant: 'horizontal', include_logo: true })}
                onChange={vi.fn()}
            />,
        );
        const logoSection = screen.getByText('Logo del negocio').closest('section')!;
        expect(within(logoSection).getByText(/posición/i)).toBeInTheDocument();
        expect(within(logoSection).getByText(/margen del logo/i)).toBeInTheDocument();
    });

    it('clicking "Horizontal" variant calls onChange with logo_variant=horizontal, include_logo=true', () => {
        const onChange = vi.fn();
        render(
            <QrPosterEditor
                payload={makePayload({ logo_variant: 'none' })}
                onChange={onChange}
            />,
        );
        const logoSection = screen.getByText('Logo del negocio').closest('section')!;
        fireEvent.click(within(logoSection).getByRole('button', { name: /horizontal/i }));
        expect(onChange).toHaveBeenCalledWith(
            expect.objectContaining({ logo_variant: 'horizontal', include_logo: true }),
        );
    });

    it('clicking "Sin logo" variant calls onChange with logo_variant=none, include_logo=false', () => {
        const onChange = vi.fn();
        render(
            <QrPosterEditor
                payload={makePayload({ logo_variant: 'horizontal', include_logo: true })}
                onChange={onChange}
            />,
        );
        const logoSection = screen.getByText('Logo del negocio').closest('section')!;
        fireEvent.click(within(logoSection).getByRole('button', { name: /sin logo/i }));
        expect(onChange).toHaveBeenCalledWith(
            expect.objectContaining({ logo_variant: 'none', include_logo: false }),
        );
    });

    it('shows missing logo warning when horizontal chosen but no horizontal URL', () => {
        mockBrandingQuery.mockReturnValue({
            data: { logo_horizontal_url: null, logo_square_url: null },
            isPending: false,
        });
        render(
            <QrPosterEditor
                payload={makePayload({ logo_variant: 'horizontal', include_logo: true })}
                onChange={vi.fn()}
            />,
        );
        expect(screen.getByText(/no tenés este logo cargado todavía/i)).toBeInTheDocument();
    });

    it('warning links to /app/resenas/configuracion#marca', () => {
        mockBrandingQuery.mockReturnValue({
            data: { logo_horizontal_url: null, logo_square_url: null },
            isPending: false,
        });
        render(
            <QrPosterEditor
                payload={makePayload({ logo_variant: 'horizontal', include_logo: true })}
                onChange={vi.fn()}
            />,
        );
        const link = screen.getByRole('link', { name: /configurar marca/i });
        expect(link).toHaveAttribute('href', '/app/resenas/configuracion#marca');
    });

    it('does NOT show missing logo warning when horizontal URL is present', () => {
        mockBrandingQuery.mockReturnValue({
            data: { logo_horizontal_url: 'https://cdn.example.com/h.png', logo_square_url: null },
            isPending: false,
        });
        render(
            <QrPosterEditor
                payload={makePayload({ logo_variant: 'horizontal', include_logo: true })}
                onChange={vi.fn()}
            />,
        );
        expect(screen.queryByText(/no tenés este logo cargado todavía/i)).not.toBeInTheDocument();
    });

    it('margin slider calls onChange with logo_margin_mm when moved', () => {
        mockBrandingQuery.mockReturnValue({
            data: { logo_horizontal_url: 'https://cdn.example.com/h.png', logo_square_url: null },
            isPending: false,
        });
        const onChange = vi.fn();
        render(
            <QrPosterEditor
                payload={makePayload({ logo_variant: 'horizontal', include_logo: true, logo_margin_mm: 8 })}
                onChange={onChange}
            />,
        );
        const logoSection = screen.getByText('Logo del negocio').closest('section')!;
        const slider = within(logoSection).getByRole('slider');
        fireEvent.change(slider, { target: { value: '15' } });
        expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ logo_margin_mm: 15 }));
    });
});
