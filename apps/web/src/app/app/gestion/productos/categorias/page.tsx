import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

import { CategoriesClient } from './categories-client';

export default async function GestionCategoriasPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canManage = session.permissions?.manage_products ?? false;

    return <CategoriesClient canManage={canManage} />;
}
