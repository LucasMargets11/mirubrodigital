import { redirect } from 'next/navigation';

/**
 * /app/menu/preview → redirects to the canonical /app/carta/publicacion.
 * Legacy route kept for backward-compatible deep links.
 */
export default function MenuPreviewPage() {
    redirect('/app/carta/publicacion');
}
