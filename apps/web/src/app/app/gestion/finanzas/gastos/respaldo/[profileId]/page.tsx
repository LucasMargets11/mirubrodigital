import { Suspense } from 'react';
import { redirect, notFound } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { getSession } from '@/lib/auth';
import { AccessMessage } from '@/components/app/access-message';
import { ReviewWorkspaceClient } from '../../tax-backup/review/review-workspace-client';

interface PageProps {
  params: Promise<{ profileId: string }>;
}

export default async function RespaldoRevisionPage({ params }: PageProps) {
  const session = await getSession();

  if (!session) {
    redirect('/entrar');
  }

  const featureEnabled = session.features?.treasury !== false;
  const canView = session.permissions?.view_finance ?? false;
  const canManage = session.permissions?.manage_finance ?? false;

  if (!featureEnabled) {
    return (
      <AccessMessage
        title="Tu plan no incluye Finanzas"
        description="Actualizá a PRO para acceder al módulo de Tesorería y Finanzas."
      />
    );
  }

  if (!canView) {
    return (
      <AccessMessage
        title="Sin acceso"
        description="Tu rol no puede ver finanzas."
        hint="Pedí acceso a un administrador"
      />
    );
  }

  const resolvedParams = await params;
  const profileId = parseInt(resolvedParams.profileId, 10);

  if (isNaN(profileId) || profileId <= 0) {
    notFound();
  }

  return (
    <Suspense
      fallback={
        <div className="flex justify-center p-12">
          <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
        </div>
      }
    >
      <ReviewWorkspaceClient profileId={profileId} canManage={canManage} />
    </Suspense>
  );
}
