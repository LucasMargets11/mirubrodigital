/** Consent category identifiers. */
export type ConsentCategory = 'necessary' | 'analytics' | 'marketing';

/** Per-category consent preferences. */
export interface ConsentPreferences {
    /** Always true — session cookies, CSRF, consent cookie itself. */
    necessary: true;
    /** Google Analytics, Hotjar, Clarity, etc. */
    analytics: boolean;
    /** Facebook Pixel, remarketing, ad scripts, etc. */
    marketing: boolean;
}

/**
 * Serialized consent state persisted in the cookie.
 * `version` enables future schema migrations without breaking existing cookies.
 */
export interface ConsentState {
    preferences: ConsentPreferences;
    /** ISO-8601 timestamp of last user action. */
    updatedAt: string;
    /** Schema version — bump when shape changes. */
    version: number;
}

/** Value exposed by ConsentProvider to consumers. */
export interface ConsentContextValue {
    /** null while reading the cookie on mount. */
    preferences: ConsentPreferences | null;
    /** true once the client has read the cookie (whether it existed or not). */
    ready: boolean;
    /** true if the user has made an explicit choice (cookie exists). */
    hasConsented: boolean;
    acceptAll: () => void;
    rejectNonEssential: () => void;
    savePreferences: (prefs: Pick<ConsentPreferences, 'analytics' | 'marketing'>) => void;
    /** Re-opens the preference modal. */
    openPreferences: () => void;
    closePreferences: () => void;
    isPreferencesOpen: boolean;
}
