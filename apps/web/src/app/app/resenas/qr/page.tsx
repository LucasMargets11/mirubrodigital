import { redirect } from 'next/navigation';
import type { Route } from 'next';

import { getSession } from '@/lib/auth';
import { ReviewQrClient } from './review-qr-client';

export default async function ResenasQrPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canView = session.permissions?.manage_reviews ?? false;
    if (!canView) {
        redirect('/app/resenas' as Route);
    }

    return (
        <ReviewQrClient businessName={session.current.business.name} />
    );
}
