import { redirect } from 'next/navigation';

/**
 * Legacy route — redirects to the canonical /app/carta.
 * Kept for backward-compatible deep links.
 */
export default function MenuHomePage() {
    redirect('/app/carta');
}
