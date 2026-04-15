import { redirect } from 'next/navigation';

/**
 * /app/menu/qr → redirects to the canonical /app/carta/publicacion.
 * Legacy route kept for backward-compatible deep links.
 */
export default function MenuQrPage() {
    redirect('/app/carta/publicacion');
}
