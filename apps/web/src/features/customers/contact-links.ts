/**
 * Links de contacto manual desde la ficha del Customer (CUSTOMER 06):
 * `https://wa.me/`, `tel:` y `mailto:`. Solo arman URLs; nunca envían nada
 * ni guardan conversación. Si un dato no se puede convertir sin adivinar,
 * devuelven null y la acción se oculta.
 */

const WHATSAPP_BASE_URL = 'https://wa.me/';

// Mismas reglas que `apps/business/whatsapp.py::normalize_whatsapp_phone` (Slice 6D).
const E164_DIGITS = /^[1-9]\d{7,14}$/;
const ALLOWED_PHONE_INPUT = /^\+?[\d\s\-().]+$/;
const AR_COUNTRY_CODE = '54';
const AR_MOBILE_PREFIX = '9';
const AR_NATIONAL_DIGITS = 10; // código de área + número, sin 0 ni 15

function normalizeAr(digits: string): string | null {
    const rest = digits.slice(AR_COUNTRY_CODE.length);
    if (rest.startsWith(AR_MOBILE_PREFIX) && rest.length === AR_NATIONAL_DIGITS + 1) return digits;
    if (rest.length === AR_NATIONAL_DIGITS && !rest.startsWith('0')) return `${AR_COUNTRY_CODE}${AR_MOBILE_PREFIX}${rest}`;
    return null;
}

/**
 * Teléfono → dígitos E.164 para WhatsApp (sin '+'), o null. Acepta formato
 * internacional (`+54 9 11 1234-5678`, `0054...`) y el nacional argentino
 * sin 15 (`011 1234-5678`, `11 1234 5678`).
 */
export function normalizeWhatsappPhone(raw: string | null | undefined): string | null {
    if (typeof raw !== 'string') return null;
    const value = raw.trim();
    if (!value || value.length > 32 || !ALLOWED_PHONE_INPUT.test(value)) return null;

    let digits = value.replace(/\D/g, '');
    let international = value.startsWith('+');
    if (!international && digits.startsWith('00')) {
        digits = digits.slice(2);
        international = true;
    }

    if (!international) {
        const national = digits.startsWith('0') ? digits.slice(1) : digits;
        if (national.length === AR_NATIONAL_DIGITS) {
            digits = `${AR_COUNTRY_CODE}${AR_MOBILE_PREFIX}${national}`;
        } else if (!digits.startsWith(AR_COUNTRY_CODE)) {
            return null;
        }
    }

    if (digits.startsWith(AR_COUNTRY_CODE)) {
        const normalized = normalizeAr(digits);
        if (normalized === null) return null;
        digits = normalized;
    }

    return E164_DIGITS.test(digits) ? digits : null;
}

/** `https://wa.me/<dígitos>` sin mensaje: el usuario escribe y envía en WhatsApp. */
export function whatsappHref(phone: string | null | undefined): string | null {
    const digits = normalizeWhatsappPhone(phone);
    return digits ? `${WHATSAPP_BASE_URL}${digits}` : null;
}

/**
 * `tel:` con el número tal como está en la ficha (solo dígitos y '+' inicial):
 * no se agrega el 9 móvil de WhatsApp porque puede ser un fijo.
 */
export function telHref(phone: string | null | undefined): string | null {
    if (typeof phone !== 'string') return null;
    const value = phone.trim();
    if (!value || !ALLOWED_PHONE_INPUT.test(value)) return null;
    const digits = value.replace(/\D/g, '');
    if (digits.length < 6 || digits.length > 15) return null;
    return `tel:${value.startsWith('+') ? '+' : ''}${digits}`;
}

const EMAIL_RE = /^[^\s@<>()",;:]+@[^\s@<>()",;:]+\.[^\s@<>()",;:]+$/;

export function mailtoHref(email: string | null | undefined): string | null {
    if (typeof email !== 'string') return null;
    const value = email.trim();
    return EMAIL_RE.test(value) ? `mailto:${value}` : null;
}
