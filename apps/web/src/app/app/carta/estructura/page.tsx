import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { canUploadMenuImages } from '@/features/menu/constants';

import { EstructuraClient } from './estructura-client';

export default async function EstructuraPage() {
    const session = await getSession();
    if (!session) redirect('/entrar');

    const canView = session.permissions?.view_menu ?? false;
    if (!canView) redirect('/app/servicios');

    const canUpload = canUploadMenuImages(
        session.features,
        session.subscription?.plan,
    );

    return <EstructuraClient canUploadImages={canUpload} />;
}
