import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

import { CashHomeClient } from './cash-home-client';

export default async function OperacionCajaHomePage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolvedSession = session as Session;
    const canManage = resolvedSession.permissions?.manage_cash ?? false;
    const canCollect = resolvedSession.permissions?.manage_cash ?? false;

    return <CashHomeClient canManage={canManage} canCollect={canCollect} />;
}
