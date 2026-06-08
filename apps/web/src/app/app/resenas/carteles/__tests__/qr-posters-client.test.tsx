/**
 * HOTFIX-RI-REVIEWS-CARTELES — Carteles access gating.
 *
 * Regression for the bug where Carteles silently redirected to /app/resenas/qr
 * for any non-Pro business. Restaurante Inteligente includes Carteles, so the
 * gate is now `print_posters_allowed` (Pro standalone OR bundle) and a blocked
 * state is shown instead of redirecting.
 *
 * Asserts:
 *   • print_posters_allowed=true  → editor renders (no redirect, no block).
 *   • print_posters_allowed=false → clear blocked state, NO redirect.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const replaceMock = vi.fn();
const pushMock = vi.fn();

vi.mock('next/navigation', () => ({
    useRouter: () => ({ replace: replaceMock, push: pushMock }),
}));

vi.mock('next/link', () => ({
    default: ({ children, href }: any) =>
        React.createElement('a', { href: typeof href === 'string' ? href : href.pathname }, children),
}));

vi.mock('@/features/reviews/api', () => ({
    getReviewSettings: vi.fn(),
}));

// Stub the heavy editor/preview/designs subtree.
vi.mock('@/features/reviews/qr-posters/components/QrPosterEditor', () => ({
    QrPosterEditor: () => React.createElement('div', { 'data-testid': 'poster-editor' }, 'Editor'),
}));
vi.mock('@/features/reviews/qr-posters/components/QrPosterPreview', () => ({
    QrPosterPreview: () => React.createElement('div', { 'data-testid': 'poster-preview' }, 'Preview'),
}));
vi.mock('@/features/reviews/qr-posters/components/SavedDesignsPanel', () => ({
    SavedDesignsPanel: () => React.createElement('div', { 'data-testid': 'saved-designs' }, 'Designs'),
}));

import { getReviewSettings } from '@/features/reviews/api';
import { QrPostersClient } from '../qr-posters-client';

const mockSettings = getReviewSettings as ReturnType<typeof vi.fn>;

function makeConfig(overrides: any = {}) {
    return {
        enabled: true,
        mode: 'smart_filter',
        effective_mode: 'smart_filter',
        google_place_id: '',
        redirect_url: '',
        redirect_threshold: 4,
        thank_you_message: '',
        is_reviews_pro: false,
        print_posters_allowed: false,
        smart_filter_allowed: true,
        trial_active: false,
        trial_available: false,
        trial_used: false,
        trial_ends_at: null,
        ...overrides,
    };
}

describe('QrPostersClient — Carteles access gating', () => {
    beforeEach(() => {
        replaceMock.mockReset();
        pushMock.mockReset();
        mockSettings.mockReset();
    });

    it('renders the editor when print_posters_allowed=true (bundle, no Pro)', async () => {
        mockSettings.mockResolvedValue(makeConfig({ is_reviews_pro: false, print_posters_allowed: true }));

        render(<QrPostersClient businessName="Demo Fast Food" />);

        await waitFor(() => {
            expect(screen.getByTestId('poster-editor')).toBeTruthy();
        });
        // Must NOT redirect to the base QR module.
        expect(replaceMock).not.toHaveBeenCalled();
        expect(pushMock).not.toHaveBeenCalled();
        expect(screen.queryByText(/no está incluido en tu plan/i)).toBeNull();
    });

    it('shows a blocked state (no redirect) when print_posters_allowed=false', async () => {
        mockSettings.mockResolvedValue(makeConfig({ is_reviews_pro: false, print_posters_allowed: false }));

        render(<QrPostersClient businessName="Plan Base" />);

        await waitFor(() => {
            expect(screen.getByText(/no está incluido en tu plan/i)).toBeTruthy();
        });
        // Critical: it must NOT bounce the user to /app/resenas/qr.
        expect(replaceMock).not.toHaveBeenCalled();
        expect(pushMock).not.toHaveBeenCalled();
        expect(screen.queryByTestId('poster-editor')).toBeNull();
    });

    it('renders the editor for Pro standalone (is_reviews_pro=true)', async () => {
        mockSettings.mockResolvedValue(makeConfig({ is_reviews_pro: true, print_posters_allowed: true }));

        render(<QrPostersClient businessName="QR Reseñas Pro" />);

        await waitFor(() => {
            expect(screen.getByTestId('poster-editor')).toBeTruthy();
        });
        expect(replaceMock).not.toHaveBeenCalled();
    });
});
