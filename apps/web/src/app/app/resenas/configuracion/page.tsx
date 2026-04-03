import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { ReviewConfigClient } from './review-config-client';

export default async function ResenasConfiguracionPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canManage = session.permissions?.manage_menu ?? false;
    if (!canManage) {
        redirect('/app/resenas');
    }

    return <ReviewConfigClient />;
}
