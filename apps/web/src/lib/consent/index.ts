export { ConsentProvider, useConsent, useConsentGate } from './ConsentProvider';
export { readConsent, writeConsent, clearConsent } from './storage';
export type { ConsentCategory, ConsentPreferences, ConsentState, ConsentContextValue } from './types';
export {
    CONSENT_COOKIE_NAME,
    CONSENT_VERSION,
    DEFAULT_PREFERENCES,
    ALL_ACCEPTED,
    SUPPRESSED_ROUTES,
    COMPACT_BANNER_ROUTES,
} from './constants';
