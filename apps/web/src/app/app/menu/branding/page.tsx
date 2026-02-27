import { redirect } from 'next/navigation';

/**
 * /app/menu/branding → redirects to the full online-menu branding settings page.
 * The branding editor already lives at /app/settings/online-menu.
 */
export default function MenuBrandingRedirectPage() {
    redirect('/app/settings/online-menu');
}
