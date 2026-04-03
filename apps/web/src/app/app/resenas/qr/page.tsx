import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { ReviewQrClient } from './review-qr-client';

export default async function ResenasQrPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canView = session.permissions?.manage_menu ?? false;
    if (!canView) {
        redirect('/app/resenas');
    }

    return (
        <ReviewQrClient businessName={session.current.business.name} />
    );
}
