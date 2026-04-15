import { redirect } from 'next/navigation';

/**
 * /app/menu/branding → redirects to the canonical /app/carta/apariencia.
 * Legacy route kept for backward-compatible deep links.
 */
export default function MenuBrandingRedirectPage() {
    redirect('/app/carta/apariencia');
}
