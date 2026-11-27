import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { ReceptionistConfigForm } from '@/features/reception/receptionist-config-form';
import { getSession } from '@/lib/auth';

/**
 * PROD-08B — «Mi agente»: configuración individual de Recepcionista IA del
 * negocio activo (`/api/v1/receptionist-config/`). El layout ya exige el
 * servicio `reception`; la edición exige `manage_agent_channels` (owner/admin)
 * y el backend vuelve a validar permiso y entitlement `reception.ai`.
 */
export default async function RecepcionistaConfiguracionPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    if (session.permissions?.manage_agent_channels !== true) {
        return (
            <AccessMessage
                title="Sin acceso"
                description="Tu rol no puede administrar la configuración del agente."
                hint="Solicitá permisos a un administrador"
            />
        );
    }

    const business = session.current.business;

    return (
        <section className="space-y-4">
            <header>
                <h1 className="text-2xl font-semibold text-slate-900">Mi agente</h1>
                <p className="text-sm text-slate-500">
                    Cómo se presenta tu Recepcionista IA y qué responde a tus clientes.
                </p>
            </header>
            <ReceptionistConfigForm
                target={{ kind: 'business', businessId: business.id }}
                businessName={business.name}
                canEdit
            />
        </section>
    );
}
