'use client';

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import type { Route } from 'next';
import {
  FileText,
  FilePlus,
  Eye,
  Clock,
  Archive,
  Edit,
  ExternalLink,
  AlertTriangle,
  Search,
} from 'lucide-react';

import { StatCard } from '@/components/admin/stat-card';
import { DataTable, type DataTableColumn } from '@/components/admin/data-table';
import { Pagination } from '@/components/admin/pagination';
import { StatusBadge } from '@/components/admin/status-badge';
import { EmptyState } from '@/components/admin/empty-state';
import { ErrorState } from '@/components/admin/error-state';
import {
  blogStatusLabel,
  blogStatusColor,
  formatDate,
  formatRelativeTime,
} from '@/lib/admin/display';
import type {
  AdminBlogPostList,
  AdminBlogPostRow,
  AdminBlogPostKPIs,
  AdminBlogCategory,
} from '@/lib/admin/types';

type Props = {
  initialData: AdminBlogPostList | null;
  kpis: AdminBlogPostKPIs | null;
  categories: AdminBlogCategory[];
  initialParams: Record<string, string>;
};

export function BlogContent({ initialData, kpis, categories, initialParams }: Props) {
  const router = useRouter();

  const [search, setSearch] = useState(initialParams.search ?? '');
  const [statusFilter, setStatusFilter] = useState(initialParams.status ?? '');
  const [categoryFilter, setCategoryFilter] = useState(initialParams.category ?? '');
  const [sortField, setSortField] = useState(initialParams.sort ?? '-updated_at');

  const currentPage = initialData?.page ?? 1;
  const totalPages = initialData?.total_pages ?? 1;

  const navigateWithParams = useCallback(
    (overrides: Record<string, string>) => {
      const params = new URLSearchParams();
      const merged = {
        search,
        status: statusFilter,
        category: categoryFilter,
        sort: sortField,
        ...overrides,
      };
      for (const [k, v] of Object.entries(merged)) {
        if (v) params.set(k, v);
      }
      router.push(`/admin/blog?${params.toString()}` as Route);
    },
    [search, statusFilter, categoryFilter, sortField, router],
  );

  const handleSearchSubmit = useCallback(() => {
    navigateWithParams({ search, page: '1' });
  }, [search, navigateWithParams]);

  const columns: DataTableColumn<AdminBlogPostRow>[] = [
    {
      key: 'title',
      header: 'Título',
      render: (row) => (
        <div className="max-w-xs">
          <Link
            href={`/admin/blog/${row.id}` as Route}
            className="truncate font-medium text-brand-600 hover:underline block"
          >
            {row.title}
          </Link>
          <p className="text-xs text-slate-500 truncate">/{row.slug}</p>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Estado',
      render: (row) => (
        <div className="flex flex-col gap-1">
          <StatusBadge label={blogStatusLabel(row.status)} colorClass={blogStatusColor(row.status)} />
          {!row.seo_complete && (
            <span className="inline-flex items-center gap-1 text-xs text-amber-600">
              <AlertTriangle className="h-3 w-3" />
              SEO incompleto
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'category_label',
      header: 'Categoría',
      render: (row) => (
        <span className="text-sm">{row.category_label ?? '—'}</span>
      ),
    },
    {
      key: 'author_name',
      header: 'Autor',
      render: (row) => (
        <span className="text-sm">{row.author_name ?? '—'}</span>
      ),
    },
    {
      key: 'published_at',
      header: 'Publicación',
      render: (row) => {
        if (row.status === 'scheduled' && row.scheduled_publish_at) {
          return (
            <span className="text-xs text-blue-600">
              Programado: {formatDate(row.scheduled_publish_at)}
            </span>
          );
        }
        return <span className="text-sm">{row.published_at ? formatDate(row.published_at) : '—'}</span>;
      },
    },
    {
      key: 'updated_at',
      header: 'Actualizado',
      render: (row) => (
        <span className="text-xs text-slate-500">{formatRelativeTime(row.updated_at)}</span>
      ),
    },
    {
      key: 'actions',
      header: '',
      render: (row) => (
        <div className="flex items-center gap-1">
          <Link
            href={`/admin/blog/${row.id}` as Route}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            title="Editar"
          >
            <Edit className="h-4 w-4" />
          </Link>
          {row.status === 'published' && (
            <a
              href={`/blog/${row.slug}`}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              title="Ver en blog"
            >
              <ExternalLink className="h-4 w-4" />
            </a>
          )}
        </div>
      ),
    },
  ];

  if (!initialData) {
    return <ErrorState message="No se pudo cargar el listado de posts." />;
  }

  return (
    <>
      {/* KPIs */}
      {kpis && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-5">
          <StatCard title="Total" value={kpis.total} icon={FileText} />
          <StatCard title="Borradores" value={kpis.draft} icon={FilePlus} />
          <StatCard title="Publicados" value={kpis.published} icon={Eye} />
          <StatCard title="Programados" value={kpis.scheduled} icon={Clock} />
          <StatCard title="Archivados" value={kpis.archived} icon={Archive} />
        </div>
      )}

      {/* Filters + Actions */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-1 flex-wrap items-center gap-2">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Buscar por título, slug, autor..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearchSubmit()}
              className="w-full rounded-md border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          {/* Status filter */}
          <select
            value={statusFilter}
            onChange={(e) => navigateWithParams({ status: e.target.value, page: '1' })}
            className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
          >
            <option value="">Todos los estados</option>
            <option value="draft">Borrador</option>
            <option value="published">Publicado</option>
            <option value="scheduled">Programado</option>
            <option value="archived">Archivado</option>
          </select>

          {/* Category filter */}
          <select
            value={categoryFilter}
            onChange={(e) => navigateWithParams({ category: e.target.value, page: '1' })}
            className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
          >
            <option value="">Todas las categorías</option>
            {categories.map((cat) => (
              <option key={cat.slug} value={cat.slug}>
                {cat.label}
              </option>
            ))}
          </select>

          {/* Sort */}
          <select
            value={sortField}
            onChange={(e) => navigateWithParams({ sort: e.target.value, page: '1' })}
            className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
          >
            <option value="-updated_at">Más reciente</option>
            <option value="-published_at">Publicación (desc)</option>
            <option value="published_at">Publicación (asc)</option>
            <option value="-created_at">Creación (desc)</option>
            <option value="title">Título A–Z</option>
            <option value="-title">Título Z–A</option>
          </select>
        </div>

        <Link
          href={"/admin/blog/nuevo" as Route}
          className="inline-flex items-center gap-2 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
        >
          <FilePlus className="h-4 w-4" />
          Nuevo post
        </Link>
      </div>

      {/* Table */}
      {initialData.results.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-12 w-12" />}
          title="Sin posts"
          description="No se encontraron posts que coincidan con los filtros aplicados."
        />
      ) : (
        <>
          <DataTable
            columns={columns}
            data={(initialData.results ?? []) as (AdminBlogPostRow & Record<string, unknown>)[]}
            keyExtractor={(row) => row.id as string}
            onRowClick={(row) => router.push(`/admin/blog/${row.id}` as Route)}
          />
          <Pagination
            page={currentPage}
            totalPages={totalPages}
            onPageChange={(p) => navigateWithParams({ page: String(p) })}
          />
        </>
      )}
    </>
  );
}
