import { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { getAdminSession, getAdminNotifications } from '@/lib/admin';
import { NotificacionesContent } from './notificaciones-content';

export const metadata: Metadata = {
  title: 'Notificaciones | Mi Rubro Admin',
};

type Props = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function AdminNotificacionesPage({ searchParams }: Props) {
  const session = await getAdminSession();
  if (!session) redirect('/admin/login');
  if (!session.authorized_sections.includes('notificaciones')) redirect('/admin/dashboard');

  const raw = await searchParams;

  // Extract and normalize query params
  const status = typeof raw.status === 'string' ? raw.status : undefined;
  const severity = typeof raw.severity === 'string' ? raw.severity : undefined;
  const type = typeof raw.type === 'string' ? raw.type : undefined;
  const page = typeof raw.page === 'string' ? parseInt(raw.page, 10) || 1 : 1;

  const initialData = await getAdminNotifications({
    status: status as any,
    severity: severity as any,
    type: type as any,
    page,
  });

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Notificaciones"
        description="Centro de notificaciones del panel interno."
      />
      <NotificacionesContent
        initialData={initialData}
        initialParams={{ status, severity, type, page: String(page) }}
      />
    </div>
  );
}
