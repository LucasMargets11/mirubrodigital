import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { EmptyState } from '@/components/admin/empty-state';
import { FileText } from 'lucide-react';

export const metadata = {
  title: 'Blog | Mi Rubro Admin',
};

export default function AdminBlogPage() {
  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Blog"
        description="Gestión de artículos, novedades y contenido del blog de Mi Rubro."
      />

      <EmptyState
        icon={<FileText className="h-12 w-12" />}
        title="Módulo de blog"
        description="Próximamente podrás crear, editar y publicar artículos del blog desde aquí."
      />
    </div>
  );
}
