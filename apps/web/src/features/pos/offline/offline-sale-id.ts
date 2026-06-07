/**
 * Stable client-side identifier generation for offline POS sales (PR-OFF-04).
 *
 * `client_order_id` is the idempotency key the backend already understands
 * (Sale.client_order_id, Fase 0). It MUST be a valid UUID so that, once we sync
 * in PR-OFF-05, retries with the same id never duplicate a sale.
 */

/** RFC4122 v4 UUID regex. */
const UUID_V4_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/**
 * Generates a UUID v4. Uses `crypto.randomUUID()` when available, otherwise
 * falls back to `crypto.getRandomValues`, and finally to a Math.random-based
 * generator. The result is always a syntactically valid v4 UUID.
 */
export function generateClientOrderId(): string {
  const c: Crypto | undefined =
    typeof globalThis !== 'undefined' ? globalThis.crypto : undefined;

  if (c && typeof c.randomUUID === 'function') {
    return c.randomUUID();
  }

  if (c && typeof c.getRandomValues === 'function') {
    const bytes = new Uint8Array(16);
    c.getRandomValues(bytes);
    // Per RFC4122 §4.4: set version (4) and variant (10xx) bits.
    bytes[6] = (bytes[6]! & 0x0f) | 0x40;
    bytes[8] = (bytes[8]! & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0'));
    return (
      hex.slice(0, 4).join('') +
      '-' +
      hex.slice(4, 6).join('') +
      '-' +
      hex.slice(6, 8).join('') +
      '-' +
      hex.slice(8, 10).join('') +
      '-' +
      hex.slice(10, 16).join('')
    );
  }

  // Last-resort fallback (non-cryptographic). Still a valid v4 UUID shape.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (ch) => {
    const r = (Math.random() * 16) | 0;
    const v = ch === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/** Returns true when `value` is a valid v4 UUID. */
export function isValidClientOrderId(value: string): boolean {
  return UUID_V4_RE.test(value);
}

/** Short, human-friendly prefix of a client_order_id for compact UI display. */
export function shortClientOrderId(clientOrderId: string): string {
  return clientOrderId.slice(0, 8);
}
