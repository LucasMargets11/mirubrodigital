import { redirect } from 'next/navigation';

/**
 * /app/settings/online-menu → redirects to the canonical /app/carta hub.
 * The mega-page has been split into /app/carta/* sub-pages.
 * Legacy route kept for backward-compatible deep links.
 */
export default function OnlineMenuSettingsPage() {
    redirect('/app/carta');
}
