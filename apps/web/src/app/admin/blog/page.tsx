import { Metadata } from 'next';

import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { getAdminBlogPosts, getAdminBlogPostKPIs, getAdminBlogCategories } from '@/lib/admin';
import { BlogContent } from './blog-content';

export const metadata: Metadata = {
  title: 'Blog | Mi Rubro Admin',
};

type Props = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function AdminBlogPage({ searchParams }: Props) {
  const raw = await searchParams;
  const params: Record<string, string> = {};
  for (const [k, v] of Object.entries(raw)) {
    if (typeof v === 'string') params[k] = v;
  }

  const [posts, kpis, categoriesRes] = await Promise.all([
    getAdminBlogPosts(params),
    getAdminBlogPostKPIs(),
    getAdminBlogCategories(),
  ]);

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Blog"
        description="Gestión de artículos, novedades y contenido del blog de Mi Rubro."
      />
      <BlogContent
        initialData={posts}
        kpis={kpis}
        categories={categoriesRes?.results ?? []}
        initialParams={params}
      />
    </div>
  );
}
