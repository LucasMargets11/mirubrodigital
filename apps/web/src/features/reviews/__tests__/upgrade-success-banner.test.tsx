/**
 * PR-A — UpgradeSuccessBanner gating regression test.
 *
 * Ensures the banner uses `is_reviews_pro` (not the deprecated
 * `smart_filter_allowed` which after PR-A is True for Base too) to detect
 * whether the upgrade has finished.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';

import { UpgradeSuccessBanner } from '../upgrade-success-banner';
import type { ReviewConfig } from '../types';

vi.mock('next/navigation', () => ({
    useRouter: () => ({ replace: vi.fn() }),
}));

vi.mock('@/features/reviews/api', () => ({
    getReviewSettings: vi.fn(),
}));

import { getReviewSettings } from '@/features/reviews/api';

const mockGet = getReviewSettings as ReturnType<typeof vi.fn>;

function makeConfig(overrides: Partial<ReviewConfig> = {}): ReviewConfig {
    return {
        enabled: true,
        mode: 'smart_filter',
        effective_mode: 'smart_filter',
        google_place_id: '',
        redirect_url: '',
        redirect_threshold: 4,
        thank_you_message: '',
        is_reviews_pro: false,
        smart_filter_allowed: true,
        trial_active: false,
        trial_available: true,
        trial_used: false,
        trial_ends_at: null,
        ...(overrides as any),
    } as ReviewConfig;
}

describe('UpgradeSuccessBanner — PR-A polling contract', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        mockGet.mockReset();
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('shows "activating" when initial config is Base (is_reviews_pro=false), even if smart_filter_allowed=true', () => {
        render(
            <UpgradeSuccessBanner
                initialConfig={makeConfig({ is_reviews_pro: false, smart_filter_allowed: true })}
            />,
        );
        expect(screen.getByText(/Procesando tu upgrade/i)).toBeTruthy();
    });

    it('shows "success" immediately when initial config is already Pro', () => {
        render(
            <UpgradeSuccessBanner
                initialConfig={makeConfig({ is_reviews_pro: true, smart_filter_allowed: true })}
            />,
        );
        expect(screen.queryByText(/Procesando tu upgrade/i)).toBeNull();
    });

    it('confirms upgrade only when polled config flips is_reviews_pro to true', async () => {
        const onConfirmed = vi.fn();
        // First poll → still Base; second poll → Pro
        mockGet
            .mockResolvedValueOnce(makeConfig({ is_reviews_pro: false, smart_filter_allowed: true }))
            .mockResolvedValueOnce(makeConfig({ is_reviews_pro: true, smart_filter_allowed: true }));

        render(
            <UpgradeSuccessBanner
                initialConfig={makeConfig({ is_reviews_pro: false })}
                onUpgradeConfirmed={onConfirmed}
            />,
        );

        // Advance two poll cycles
        await act(async () => {
            await vi.advanceTimersByTimeAsync(2000);
        });
        expect(onConfirmed).not.toHaveBeenCalled();

        await act(async () => {
            await vi.advanceTimersByTimeAsync(2000);
        });

        expect(onConfirmed).toHaveBeenCalledTimes(1);
        expect(onConfirmed.mock.calls[0][0].is_reviews_pro).toBe(true);
    });
});
