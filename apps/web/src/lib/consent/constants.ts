import type { ConsentPreferences } from './types';

/** Cookie name for consent preferences. */
export const CONSENT_COOKIE_NAME = 'mirubro_consent';

/** Current schema version. Bump on breaking changes to ConsentState. */
export const CONSENT_VERSION = 1;

/** Cookie max-age in seconds (365 days). */
export const CONSENT_MAX_AGE = 365 * 24 * 60 * 60;

/** Default preferences before explicit user choice. */
export const DEFAULT_PREFERENCES: ConsentPreferences = {
    necessary: true,
    analytics: false,
    marketing: false,
};

/** All-accepted preferences. */
export const ALL_ACCEPTED: ConsentPreferences = {
    necessary: true,
    analytics: true,
    marketing: true,
};

/** Route prefixes where the banner should NOT be shown. */
export const SUPPRESSED_ROUTES = ['/app', '/admin', '/pos', '/q', '/plantillas'];

/** Route prefixes that get the compact banner variant. */
export const COMPACT_BANNER_ROUTES = ['/m'];
