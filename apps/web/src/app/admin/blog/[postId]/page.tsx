import { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { getAdminBlogPostDetail, getAdminBlogCategories } from '@/lib/admin';
import { BlogPostForm } from '../_components/blog-post-form';

export const metadata: Metadata = {
  title: 'Editar post | Mi Rubro Admin',
};

type Props = {
  params: Promise<{ postId: string }>;
};

export default async function AdminBlogEditPage({ params }: Props) {
  const { postId } = await params;

  const [post, categoriesRes] = await Promise.all([
    getAdminBlogPostDetail(postId),
    getAdminBlogCategories(),
  ]);

  if (!post) notFound();

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title={post.title || 'Post sin título'}
        description={`ID: ${post.id} · /${post.slug}`}
      />
      <BlogPostForm
        mode="edit"
        post={post}
        categories={categoriesRes?.results ?? []}
      />
    </div>
  );
}
