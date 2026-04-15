import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { canUploadMenuImages } from '@/features/menu/constants';

import { AparienciaClient } from './apariencia-client';

export default async function AparienciaPage() {
    const session = await getSession();
    if (!session) redirect('/entrar');

    const canView = session.permissions?.view_menu ?? false;
    if (!canView) redirect('/app/servicios');

    const canUpload = canUploadMenuImages(
        session.features,
        session.subscription?.plan,
    );

    return <AparienciaClient canUploadImages={canUpload} />;
}
