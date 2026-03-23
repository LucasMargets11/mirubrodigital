import { Metadata } from 'next';

import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { getAdminBlogCategories } from '@/lib/admin';
import { BlogPostForm } from '../_components/blog-post-form';

export const metadata: Metadata = {
  title: 'Nuevo post | Mi Rubro Admin',
};

export default async function AdminBlogNuevoPage() {
  const categoriesRes = await getAdminBlogCategories();

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Nuevo post"
        description="Crear un nuevo artículo para el blog de Mi Rubro."
        backHref="/admin/blog"
        backLabel="Blog"
      />
      <BlogPostForm
        mode="create"
        categories={categoriesRes?.results ?? []}
      />
    </div>
  );
}
