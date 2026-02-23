import { redirect } from 'next/navigation';
import { ReactNode } from 'react';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { ProductsLayout } from './products-layout';

export default async function GestionProductosLayout({ children }: { children: ReactNode }) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.products !== false;
    const canView = session.permissions?.view_products ?? false;
    const canManage = session.permissions?.manage_products ?? false;

    if (!featureEnabled) {
        return (
            <AccessMessage 
                title="Tu plan no incluye Productos" 
                description="Actualizá el plan o hablá con tu ejecutivo para habilitar el módulo de catálogo." 
            />
        );
    }

    if (!canView) {
        return (
            <AccessMessage 
                title="Sin acceso" 
                description="Tu rol no tiene permiso para ver el catálogo." 
                hint="Pedí acceso a un administrador" 
            />
        );
    }

    return (
        <ProductsLayout canManage={canManage} canCreate={canManage}>
            {children}
        </ProductsLayout>
    );
}
