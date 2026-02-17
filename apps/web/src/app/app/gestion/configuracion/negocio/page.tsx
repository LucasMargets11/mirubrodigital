import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { BusinessSettingsClient } from './business-settings-client';

export default async function BusinessSettingsPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.settings !== false;
    const canManage = session.permissions?.manage_commercial_settings ?? false;

    if (!featureEnabled) {
        return (
            <AccessMessage
                title="Tu plan no incluye Configuración"
                description="Actualizá tu plan para habilitar las opciones avanzadas de gestión."
            />
        );
    }

    if (!canManage) {
        return (
            <AccessMessage
                title="Sin acceso"
                description="Tu rol no tiene permiso para editar la configuración del negocio."
                hint="Pedí acceso a un administrador"
            />
        );
    }

    return <BusinessSettingsClient />;
}
