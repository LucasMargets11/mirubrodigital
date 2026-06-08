/**
 * PR-A — Nav gating regression.
 *
 * For a Base user (is_reviews_pro=false, print_posters_allowed=false):
 *   • Feedback tab is visible.
 *   • Carteles tab is NOT visible.
 *   • Analytics tab is NOT visible.
 *
 * For a Pro user (is_reviews_pro=true, print_posters_allowed=true):
 *   • Feedback, Carteles and Analytics are all visible.
 *
 * For a Restaurante Inteligente bundle user (is_reviews_pro=false but
 * print_posters_allowed=true):
 *   • Carteles tab is visible (Carteles is included in the bundle).
 *   • Analytics tab stays hidden (Pro-only).
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('next/link', () => ({
    default: ({ children, href }: any) =>
        React.createElement('a', { href: typeof href === 'string' ? href : href.pathname }, children),
}));

vi.mock('next/navigation', () => ({
    usePathname: () => '/app/resenas',
}));

vi.mock('@/features/reviews/api', () => ({
    getReviewSettings: vi.fn(),
    getReviewStats: vi.fn(),
}));

import { getReviewSettings, getReviewStats } from '@/features/reviews/api';
import { ResenasNav } from '../resenas-nav';

const mockSettings = getReviewSettings as ReturnType<typeof vi.fn>;
const mockStats = getReviewStats as ReturnType<typeof vi.fn>;

function baseConfig(overrides: any = {}) {
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

describe('ResenasNav — PR-A gating', () => {
    beforeEach(() => {
        mockSettings.mockReset();
        mockStats.mockReset();
        mockStats.mockResolvedValue({ total_reviews: 0, new_reviews: 0 });
    });

    it('Base user: Feedback visible, Carteles and Analytics hidden', async () => {
        mockSettings.mockResolvedValue(baseConfig({ is_reviews_pro: false }));

        render(<ResenasNav />);

        await waitFor(() => {
            expect(screen.getByText('Feedback')).toBeTruthy();
        });

        expect(screen.queryByText('Carteles')).toBeNull();
        expect(screen.queryByText('Analytics')).toBeNull();
    });

    it('Pro user: Feedback, Carteles and Analytics all visible', async () => {
        mockSettings.mockResolvedValue(baseConfig({ is_reviews_pro: true, print_posters_allowed: true }));

        render(<ResenasNav />);

        await waitFor(() => {
            expect(screen.getByText('Carteles')).toBeTruthy();
        });
        expect(screen.getByText('Feedback')).toBeTruthy();
        expect(screen.getByText('Analytics')).toBeTruthy();
    });

    it('Base user with smart_filter_allowed=true must NOT see Analytics (regression for PR-A)', async () => {
        // This catches the previous bug where Analytics was gated on
        // smart_filter_allowed instead of is_reviews_pro.
        mockSettings.mockResolvedValue(
            baseConfig({ is_reviews_pro: false, smart_filter_allowed: true, trial_active: false }),
        );

        render(<ResenasNav />);

        await waitFor(() => {
            expect(screen.getByText('Feedback')).toBeTruthy();
        });
        expect(screen.queryByText('Analytics')).toBeNull();
    });

    it('Restaurante Inteligente bundle: Carteles visible, Analytics hidden', async () => {
        // Bundle plans include Carteles (print_posters_allowed=true) but are not
        // on the Pro tier (is_reviews_pro=false), so Analytics stays hidden.
        mockSettings.mockResolvedValue(
            baseConfig({ is_reviews_pro: false, print_posters_allowed: true }),
        );

        render(<ResenasNav />);

        await waitFor(() => {
            expect(screen.getByText('Carteles')).toBeTruthy();
        });
        expect(screen.getByText('Feedback')).toBeTruthy();
        expect(screen.queryByText('Analytics')).toBeNull();
    });
});
