import { redirect } from 'next/navigation';

import { AppPageHeader } from '@/components/navigation/app-page-header';
import { CommunicationAutomationCard } from '@/features/appointments/communication-automation-card';
import { PublicBookingLinkCard } from '@/features/appointments/public-booking-link-card';
import { ReminderAutomationCard } from '@/features/appointments/reminder-automation-card';
import { ReplyToEmailCard } from '@/features/appointments/reply-to-email-card';
import { MercadoPagoConnectionCard, type MercadoPagoReturn } from '@/features/merchant-payments/mercado-pago-connection-card';
import { canManageMercadoPago, canViewMercadoPago } from '@/features/merchant-payments/permissions';
import { getSession } from '@/lib/auth';

type Props = {
    searchParams?: Promise<{ mp?: string | string[] }>;
};

function parseMpReturn(value: string | string[] | undefined): MercadoPagoReturn {
    // Solo dos valores cerrados; cualquier otra cosa se ignora.
    return value === 'connected' || value === 'error' ? value : null;
}

export default async function TurnosConfiguracionPage({ searchParams }: Props) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const params = (await searchParams) ?? {};
    const canView = canViewMercadoPago(session);
    const canManage = canManageMercadoPago(session);
    // CUSTOMER 07B: ver = `manage_settings` en Turnos (owner/admin/manager);
    // cambiar = `manage_reminder_automations` (owner/admin). Mismo gate que el backend.
    const canViewAutomations = Boolean(session.permissions?.manage_settings && session.permissions?.view_appointments);
    const canManageAutomations = Boolean(session.permissions?.manage_reminder_automations);

    return (
        <section className="space-y-4">
            <AppPageHeader
                title="Configuración"
                description="Página de reservas, cobros online de señas y recordatorios automáticos."
            />
            {/* 7B.4: visible para todo rol con acceso a Turnos; no es un dato financiero. */}
            <PublicBookingLinkCard publicBooking={session.current.business.public_booking} />
            <MercadoPagoConnectionCard
                context="appointments"
                canView={canView}
                canManage={canManage}
                mpReturn={parseMpReturn(params.mp)}
            />
            {canViewAutomations ? <ReminderAutomationCard canManage={canManageAutomations} /> : null}
            {/* CUSTOMER 07D.3A.1: Reply-To de los emails al cliente; mismo gate que las automatizaciones. */}
            {canViewAutomations ? <ReplyToEmailCard canManage={canManageAutomations} /> : null}
            {/* CUSTOMER 07D.4A: emails automáticos al cliente (apagados por defecto); mismo gate. */}
            {canViewAutomations ? <CommunicationAutomationCard canManage={canManageAutomations} /> : null}
        </section>
    );
}
