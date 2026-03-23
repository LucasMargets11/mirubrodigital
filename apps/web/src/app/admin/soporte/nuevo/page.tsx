import { Metadata } from 'next';

import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { NuevoTicketForm } from './nuevo-ticket-form';

export const metadata: Metadata = {
  title: 'Nuevo Ticket | Mi Rubro Admin',
};

export default function AdminNuevoTicketPage() {
  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Nuevo ticket"
        description="Crear un ticket de soporte para un cliente."
      />
      <NuevoTicketForm />
    </div>
  );
}
