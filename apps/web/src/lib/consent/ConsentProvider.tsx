'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ConsentContextValue, ConsentPreferences } from './types';
import { ALL_ACCEPTED, DEFAULT_PREFERENCES } from './constants';
import { preferencesFromState, readConsent, writeConsent } from './storage';

const ConsentContext = createContext<ConsentContextValue | null>(null);

export function ConsentProvider({ children }: { children: React.ReactNode }) {
    const [preferences, setPreferences] = useState<ConsentPreferences | null>(null);
    const [ready, setReady] = useState(false);
    const [hasConsented, setHasConsented] = useState(false);
    const [isPreferencesOpen, setIsPreferencesOpen] = useState(false);

    // Read cookie after mount to avoid hydration mismatch.
    useEffect(() => {
        const state = readConsent();
        setPreferences(preferencesFromState(state));
        setHasConsented(state !== null);
        setReady(true);
    }, []);

    const persist = useCallback((prefs: ConsentPreferences) => {
        writeConsent(prefs);
        setPreferences(prefs);
        setHasConsented(true);
    }, []);

    const acceptAll = useCallback(() => {
        persist(ALL_ACCEPTED);
    }, [persist]);

    const rejectNonEssential = useCallback(() => {
        persist(DEFAULT_PREFERENCES);
    }, [persist]);

    const savePreferences = useCallback(
        (prefs: Pick<ConsentPreferences, 'analytics' | 'marketing'>) => {
            persist({ necessary: true, ...prefs });
            setIsPreferencesOpen(false);
        },
        [persist],
    );

    const openPreferences = useCallback(() => setIsPreferencesOpen(true), []);
    const closePreferences = useCallback(() => setIsPreferencesOpen(false), []);

    const value = useMemo<ConsentContextValue>(
        () => ({
            preferences,
            ready,
            hasConsented,
            acceptAll,
            rejectNonEssential,
            savePreferences,
            openPreferences,
            closePreferences,
            isPreferencesOpen,
        }),
        [
            preferences,
            ready,
            hasConsented,
            acceptAll,
            rejectNonEssential,
            savePreferences,
            openPreferences,
            closePreferences,
            isPreferencesOpen,
        ],
    );

    return <ConsentContext.Provider value={value}>{children}</ConsentContext.Provider>;
}

export function useConsent(): ConsentContextValue {
    const ctx = useContext(ConsentContext);
    if (!ctx) {
        throw new Error('useConsent must be used within <ConsentProvider>');
    }
    return ctx;
}

/**
 * Check if a specific consent category is currently accepted.
 * Returns false while the provider is still loading.
 *
 * Usage (future):
 *   const allowed = useConsentGate('analytics');
 *   if (allowed) { loadGA4(); }
 */
export function useConsentGate(category: 'analytics' | 'marketing'): boolean {
    const { preferences, ready } = useConsent();
    if (!ready || !preferences) return false;
    return preferences[category];
}
