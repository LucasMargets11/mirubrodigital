import type { ConsentPreferences, ConsentState } from './types';
import {
    CONSENT_COOKIE_NAME,
    CONSENT_MAX_AGE,
    CONSENT_VERSION,
    DEFAULT_PREFERENCES,
} from './constants';

/**
 * Read consent state from the cookie.
 * Returns null when the cookie does not exist or is unparseable.
 */
export function readConsent(): ConsentState | null {
    if (typeof document === 'undefined') return null;

    const raw = document.cookie
        .split('; ')
        .find((c) => c.startsWith(`${CONSENT_COOKIE_NAME}=`));
    if (!raw) return null;

    try {
        const value = decodeURIComponent(raw.split('=').slice(1).join('='));
        const parsed: unknown = JSON.parse(value);

        if (
            parsed &&
            typeof parsed === 'object' &&
            'preferences' in parsed &&
            'version' in parsed
        ) {
            return parsed as ConsentState;
        }
        return null;
    } catch {
        return null;
    }
}

/**
 * Write consent preferences to the cookie.
 */
export function writeConsent(prefs: ConsentPreferences): void {
    if (typeof document === 'undefined') return;

    const state: ConsentState = {
        preferences: { ...prefs, necessary: true },
        updatedAt: new Date().toISOString(),
        version: CONSENT_VERSION,
    };

    const value = encodeURIComponent(JSON.stringify(state));
    const isSecure = window.location.protocol === 'https:';
    const parts = [
        `${CONSENT_COOKIE_NAME}=${value}`,
        `path=/`,
        `max-age=${CONSENT_MAX_AGE}`,
        `samesite=lax`,
    ];
    if (isSecure) parts.push('secure');

    document.cookie = parts.join('; ');
}

/**
 * Remove the consent cookie (e.g. for testing or reset flows).
 */
export function clearConsent(): void {
    if (typeof document === 'undefined') return;
    document.cookie = `${CONSENT_COOKIE_NAME}=; path=/; max-age=0`;
}

/**
 * Extract preferences from stored state, falling back to defaults.
 */
export function preferencesFromState(state: ConsentState | null): ConsentPreferences {
    if (!state) return DEFAULT_PREFERENCES;
    return {
        necessary: true,
        analytics: !!state.preferences.analytics,
        marketing: !!state.preferences.marketing,
    };
}
