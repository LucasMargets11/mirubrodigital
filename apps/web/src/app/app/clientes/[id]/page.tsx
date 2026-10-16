import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { CustomerDetailClient } from './customer-detail-client';

type Props = {
    params: Promise<{ id: string }>;
};

export default async function CustomerDetailPage({ params }: Props) {
    const { id } = await params;
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    // Clientes core es compartido: Gestión (gate histórico por `sales`) o
    // cualquier plan con el flag `customers` (incluye Turnos, CUSTOMER 02).
    const customersFeatureEnabled = session.features?.customers === true || session.features?.sales !== false;
    const canViewCustomers = session.permissions?.view_customers ?? false;
    const canViewSales = session.permissions?.view_sales ?? false;
    const businessTimeZone = session.current?.business?.timezone ?? null;
    const canManageCustomers = session.permissions?.manage_customers ?? false;
    const canManageCustomerNotes = session.permissions?.manage_customer_notes ?? false;
    const canManageCustomerReminders = session.permissions?.manage_customer_reminders ?? false;
    const canManageContactPreferences = session.permissions?.manage_customer_contact_preferences ?? false;
    const quotesFeatureEnabled = session.features?.quotes !== false;
    const canViewQuotes = session.permissions?.view_quotes ?? false;
    const ordersFeatureEnabled = session.features?.orders !== false;
    const canViewOrders = session.permissions?.view_orders ?? false;
    // CUSTOMER 06: "Nuevo turno" solo con el módulo Turnos y `manage_appointments`.
    const hasTurnos = session.services?.enabled?.includes('appointments') ?? false;
    const canCreateAppointments = hasTurnos && (session.permissions?.manage_appointments ?? false);
    const canCreateCustomer = (session.permissions?.manage_customers ?? false) || (session.permissions?.create_sales ?? false);

    if (!customersFeatureEnabled) {
        return <AccessMessage title="Tu plan no incluye Clientes" description="Actualizá el plan para gestionar clientes." />;
    }

    if (!canViewCustomers) {
        return (
            <AccessMessage
                title="Sin acceso"
                description="Tu rol no puede ver la ficha del cliente."
                hint="Solicitá permisos a un administrador"
            />
        );
    }

    return (
        <CustomerDetailClient
            customerId={id}
            canManage={canManageCustomers}
            canManageNotes={canManageCustomerNotes}
            canManageReminders={canManageCustomerReminders}
            canManageContactPreferences={canManageContactPreferences}
            canViewSales={canViewSales}
            canViewQuotes={quotesFeatureEnabled && canViewQuotes}
            canViewOrders={ordersFeatureEnabled && canViewOrders}
            businessTimeZone={businessTimeZone}
            canCreateAppointments={canCreateAppointments}
            canCreateCustomer={canCreateCustomer}
        />
    );
}
