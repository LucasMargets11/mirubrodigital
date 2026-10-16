import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { AppPageHeader } from '@/components/navigation/app-page-header';
import { BusinessNotificationsPanel } from '@/features/business-notifications';
import { getSession } from '@/lib/auth';

import { TurnosClient } from './turnos-client';

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type Props = {
    searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

function single(value: string | string[] | undefined): string | undefined {
    return Array.isArray(value) ? value[0] : value;
}

export default async function TurnosListPage({ searchParams }: Props) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canView = session.permissions?.view_appointments ?? false;

    if (!canView) {
        return (
            <AccessMessage
                title="Sin acceso"
                description="Tu rol no tiene permiso para ver los turnos."
                hint="Pedí acceso a un administrador"
            />
        );
    }

    const canManage = session.permissions?.manage_appointments ?? false;
    // CUSTOMER 05: mismo gate que /app/clientes (plan + `view_customers`); el
    // alta inline exige el permiso real de crear Customers (backend valida igual).
    const customersFeatureEnabled = session.features?.customers === true || session.features?.sales !== false;
    const canPickCustomer = canManage && customersFeatureEnabled && (session.permissions?.view_customers ?? false);
    const canCreateCustomer =
        canPickCustomer && ((session.permissions?.manage_customers ?? false) || (session.permissions?.create_sales ?? false));

    // Deep link desde una notificación (Slice 6D): `?date=YYYY-MM-DD&appointment=<uuid>`.
    const params = await searchParams;
    const dateParam = single(params.date);
    const appointmentParam = single(params.appointment);
    // Slice 7D: `?view=week` abre la vista semanal (la mantiene el refresh/back).
    const initialView = single(params.view) === 'week' ? 'week' : 'day';
    const initialDate = dateParam && ISO_DATE_RE.test(dateParam) ? dateParam : undefined;
    const highlightId = appointmentParam && UUID_RE.test(appointmentParam) ? appointmentParam : undefined;

    return (
        <section className="space-y-4">
            <AppPageHeader
                title="Turnos"
                description="Reservá turnos manualmente y gestioná tu agenda del día o de la semana."
            />
            <BusinessNotificationsPanel />
            <TurnosClient
                key={`${initialView}:${initialDate ?? ''}:${highlightId ?? ''}`}
                canManage={canManage}
                canPickCustomer={canPickCustomer}
                canCreateCustomer={canCreateCustomer}
                timeZone={session.current.business.timezone}
                initialView={initialView}
                initialDate={initialDate}
                highlightId={highlightId}
            />
        </section>
    );
}
