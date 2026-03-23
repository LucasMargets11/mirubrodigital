'use client';

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import type { Route } from 'next';
import {
  Save,
  Send,
  Eye,
  Clock,
  Archive,
  ArrowLeft,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

import { SectionCard } from '@/components/admin/section-card';
import { StatusBadge } from '@/components/admin/status-badge';
import { blogStatusLabel, blogStatusColor, formatDateTime } from '@/lib/admin/display';
import type { AdminBlogPostDetail, AdminBlogCategory } from '@/lib/admin/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Props = {
  mode: 'create' | 'edit';
  post?: AdminBlogPostDetail | null;
  categories: AdminBlogCategory[];
};

async function apiCall(path: string, method: string, body?: unknown) {
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => null);
  return { ok: res.ok, status: res.status, data };
}

export function BlogPostForm({ mode, post, categories }: Props) {
  const router = useRouter();
  const refresh = useCallback(() => {
    // router.refresh() exists in Next.js App Router but may not be typed in some versions
    (router as unknown as { refresh: () => void }).refresh();
  }, [router]);
  const isEdit = mode === 'edit' && post;

  // ── Form state ─────────────────────────────────────────────────
  const [title, setTitle] = useState(post?.title ?? '');
  const [slug, setSlug] = useState(post?.slug ?? '');
  const [excerpt, setExcerpt] = useState(post?.excerpt ?? '');
  const [bodyJson, setBodyJson] = useState(
    post?.body_content ? JSON.stringify(post.body_content, null, 2) : '[]',
  );
  const [coverImageUrl, setCoverImageUrl] = useState(post?.cover_image_url ?? '');
  const [readingTime, setReadingTime] = useState(post?.reading_time ?? '');
  const [category, setCategory] = useState(post?.category_slug ?? '');
  const [tagsStr, setTagsStr] = useState((post?.tags ?? []).join(', '));

  // SEO
  const [metaTitle, setMetaTitle] = useState(post?.meta_title ?? '');
  const [metaDescription, setMetaDescription] = useState(post?.meta_description ?? '');
  const [ogTitle, setOgTitle] = useState(post?.og_title ?? '');
  const [ogDescription, setOgDescription] = useState(post?.og_description ?? '');
  const [ogImageUrl, setOgImageUrl] = useState(post?.og_image_url ?? '');
  const [canonicalUrl, setCanonicalUrl] = useState(post?.canonical_url ?? '');

  // Schedule
  const [scheduleDate, setScheduleDate] = useState('');

  // UI state
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [seoOpen, setSeoOpen] = useState(false);

  const buildPayload = useCallback(() => {
    let bodyContent: unknown[] = [];
    try {
      bodyContent = JSON.parse(bodyJson);
    } catch {
      // will be empty
    }
    const tags = tagsStr
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);
    return {
      title,
      slug: slug || undefined,
      excerpt,
      body_content: bodyContent,
      cover_image_url: coverImageUrl,
      reading_time: readingTime,
      category: category || undefined,
      tags,
      meta_title: metaTitle,
      meta_description: metaDescription,
      og_title: ogTitle,
      og_description: ogDescription,
      og_image_url: ogImageUrl,
      canonical_url: canonicalUrl,
    };
  }, [
    title, slug, excerpt, bodyJson, coverImageUrl, readingTime,
    category, tagsStr, metaTitle, metaDescription, ogTitle,
    ogDescription, ogImageUrl, canonicalUrl,
  ]);

  const handleSaveDraft = useCallback(async () => {
    setSaving(true);
    setFeedback(null);
    try {
      const payload = buildPayload();
      if (isEdit) {
        const res = await apiCall(`/api/v1/platform-admin/blog/posts/${post.id}/update/`, 'PATCH', payload);
        if (res.ok) {
          setFeedback({ type: 'success', message: 'Post guardado correctamente.' });
          refresh();
        } else {
          setFeedback({ type: 'error', message: res.data?.detail ?? 'Error al guardar.' });
        }
      } else {
        const res = await apiCall('/api/v1/platform-admin/blog/posts/create/', 'POST', payload);
        if (res.ok && res.data?.id) {
          router.push(`/admin/blog/${res.data.id}` as Route);
        } else {
          setFeedback({ type: 'error', message: res.data?.detail ?? 'Error al crear el post.' });
        }
      }
    } finally {
      setSaving(false);
    }
  }, [buildPayload, isEdit, post, router, refresh]);

  const handlePublish = useCallback(async () => {
    if (!isEdit) return;
    setSaving(true);
    setFeedback(null);
    try {
      // Save changes first
      await apiCall(`/api/v1/platform-admin/blog/posts/${post.id}/update/`, 'PATCH', buildPayload());
      // Then publish
      const res = await apiCall(`/api/v1/platform-admin/blog/posts/${post.id}/publish/`, 'POST');
      if (res.ok) {
        setFeedback({ type: 'success', message: 'Post publicado correctamente.' });
        refresh();
      } else {
        const errors = res.data?.errors?.join(', ') ?? res.data?.detail ?? 'Error al publicar.';
        setFeedback({ type: 'error', message: errors });
      }
    } finally {
      setSaving(false);
    }
  }, [isEdit, post, buildPayload, router, refresh]);

  const handleUnpublish = useCallback(async () => {
    if (!isEdit) return;
    setSaving(true);
    setFeedback(null);
    try {
      const res = await apiCall(`/api/v1/platform-admin/blog/posts/${post.id}/unpublish/`, 'POST');
      if (res.ok) {
        setFeedback({ type: 'success', message: 'Post despublicado.' });
        refresh();
      } else {
        setFeedback({ type: 'error', message: res.data?.detail ?? 'Error al despublicar.' });
      }
    } finally {
      setSaving(false);
    }
  }, [isEdit, post, refresh]);

  const handleArchive = useCallback(async () => {
    if (!isEdit) return;
    setSaving(true);
    setFeedback(null);
    try {
      const res = await apiCall(`/api/v1/platform-admin/blog/posts/${post.id}/archive/`, 'POST');
      if (res.ok) {
        setFeedback({ type: 'success', message: 'Post archivado.' });
        refresh();
      } else {
        setFeedback({ type: 'error', message: res.data?.detail ?? 'Error al archivar.' });
      }
    } finally {
      setSaving(false);
    }
  }, [isEdit, post, refresh]);

  const handleSchedule = useCallback(async () => {
    if (!isEdit || !scheduleDate) return;
    setSaving(true);
    setFeedback(null);
    try {
      // Save changes first
      await apiCall(`/api/v1/platform-admin/blog/posts/${post.id}/update/`, 'PATCH', buildPayload());
      const res = await apiCall(`/api/v1/platform-admin/blog/posts/${post.id}/schedule/`, 'POST', {
        publish_at: new Date(scheduleDate).toISOString(),
      });
      if (res.ok) {
        setFeedback({ type: 'success', message: 'Publicación programada correctamente.' });
        refresh();
      } else {
        const errors = res.data?.errors?.join(', ') ?? res.data?.detail ?? 'Error al programar.';
        setFeedback({ type: 'error', message: errors });
      }
    } finally {
      setSaving(false);
    }
  }, [isEdit, post, scheduleDate, buildPayload, router, refresh]);

  const inputClass =
    'w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500';

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      {/* Main content — 2 cols */}
      <div className="space-y-6 lg:col-span-2">
        {/* Feedback */}
        {feedback && (
          <div
            className={`flex items-center gap-2 rounded-md px-4 py-3 text-sm ${
              feedback.type === 'success'
                ? 'bg-emerald-50 text-emerald-700'
                : 'bg-red-50 text-red-700'
            }`}
          >
            {feedback.type === 'success' ? (
              <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
            ) : (
              <AlertTriangle className="h-4 w-4 flex-shrink-0" />
            )}
            {feedback.message}
          </div>
        )}

        {/* Título */}
        <SectionCard title="Contenido editorial">
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Título *</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Título del artículo"
                className={inputClass}
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Slug</label>
              <input
                type="text"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="Se genera automáticamente del título si se deja vacío"
                className={inputClass}
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Extracto *</label>
              <textarea
                value={excerpt}
                onChange={(e) => setExcerpt(e.target.value)}
                placeholder="Resumen corto (1–2 oraciones)"
                rows={2}
                className={inputClass}
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">
                Contenido (JSON ContentBlocks) *
              </label>
              <textarea
                value={bodyJson}
                onChange={(e) => setBodyJson(e.target.value)}
                placeholder='[{"type":"h2","text":"..."},{"type":"p","text":"..."}]'
                rows={12}
                className={`${inputClass} font-mono text-xs`}
              />
              <p className="mt-1 text-xs text-slate-400">
                Formato: array de bloques. Tipos soportados: h2, h3, p, ul, check, cta, faq.
              </p>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">URL de imagen de portada</label>
              <input
                type="text"
                value={coverImageUrl}
                onChange={(e) => setCoverImageUrl(e.target.value)}
                placeholder="https://... o /blog/image.svg"
                className={inputClass}
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Tiempo de lectura</label>
              <input
                type="text"
                value={readingTime}
                onChange={(e) => setReadingTime(e.target.value)}
                placeholder="5 min"
                className={inputClass}
              />
            </div>
          </div>
        </SectionCard>

        {/* SEO — Collapsible */}
        <SectionCard title="">
          <button
            type="button"
            onClick={() => setSeoOpen(!seoOpen)}
            className="flex w-full items-center justify-between text-left"
          >
            <span className="text-sm font-semibold text-slate-800">
              SEO y Open Graph
              {isEdit && post && post.seo_missing.length > 0 && (
                <span className="ml-2 inline-flex items-center gap-1 text-xs text-amber-600">
                  <AlertTriangle className="h-3 w-3" />
                  {post.seo_missing.length} campo(s) faltante(s)
                </span>
              )}
            </span>
            {seoOpen ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
          </button>
          {seoOpen && (
            <div className="mt-4 space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">Meta title</label>
                <input type="text" value={metaTitle} onChange={(e) => setMetaTitle(e.target.value)} placeholder="Título para SEO" className={inputClass} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">Meta description</label>
                <textarea value={metaDescription} onChange={(e) => setMetaDescription(e.target.value)} placeholder="Descripción para SEO" rows={2} className={inputClass} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">OG title</label>
                <input type="text" value={ogTitle} onChange={(e) => setOgTitle(e.target.value)} placeholder="Open Graph title" className={inputClass} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">OG description</label>
                <textarea value={ogDescription} onChange={(e) => setOgDescription(e.target.value)} placeholder="Open Graph description" rows={2} className={inputClass} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">OG image URL</label>
                <input type="text" value={ogImageUrl} onChange={(e) => setOgImageUrl(e.target.value)} placeholder="https://..." className={inputClass} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">Canonical URL</label>
                <input type="text" value={canonicalUrl} onChange={(e) => setCanonicalUrl(e.target.value)} placeholder="https://www.mirubro.com/blog/..." className={inputClass} />
              </div>
            </div>
          )}
        </SectionCard>
      </div>

      {/* Sidebar — 1 col */}
      <div className="space-y-6">
        {/* Status & actions */}
        <SectionCard title="Estado editorial">
          <div className="space-y-4">
            {isEdit && (
              <div>
                <StatusBadge label={blogStatusLabel(post.status)} colorClass={blogStatusColor(post.status)} />
              </div>
            )}

            {/* Save draft */}
            <button
              type="button"
              onClick={handleSaveDraft}
              disabled={saving || !title.trim()}
              className="flex w-full items-center justify-center gap-2 rounded-md bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              <Save className="h-4 w-4" />
              {isEdit ? 'Guardar cambios' : 'Guardar borrador'}
            </button>

            {/* Publish */}
            {isEdit && (post.status === 'draft' || post.status === 'scheduled') && (
              <button
                type="button"
                onClick={handlePublish}
                disabled={saving}
                className="flex w-full items-center justify-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                <Send className="h-4 w-4" />
                Publicar ahora
              </button>
            )}

            {/* Unpublish */}
            {isEdit && post.status === 'published' && (
              <button
                type="button"
                onClick={handleUnpublish}
                disabled={saving}
                className="flex w-full items-center justify-center gap-2 rounded-md border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                <ArrowLeft className="h-4 w-4" />
                Despublicar
              </button>
            )}

            {/* Archive */}
            {isEdit && post.status !== 'archived' && (
              <button
                type="button"
                onClick={handleArchive}
                disabled={saving}
                className="flex w-full items-center justify-center gap-2 rounded-md border border-slate-200 px-4 py-2 text-sm font-medium text-slate-500 hover:bg-slate-50 disabled:opacity-50"
              >
                <Archive className="h-4 w-4" />
                Archivar
              </button>
            )}

            {/* Unarchive (back to draft) */}
            {isEdit && post.status === 'archived' && (
              <button
                type="button"
                onClick={handleUnpublish}
                disabled={saving}
                className="flex w-full items-center justify-center gap-2 rounded-md border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                <ArrowLeft className="h-4 w-4" />
                Volver a borrador
              </button>
            )}

            {/* Schedule */}
            {isEdit && (post.status === 'draft' || post.status === 'scheduled') && (
              <div className="border-t border-slate-100 pt-3">
                <label className="mb-1 block text-xs font-medium text-slate-600">
                  Programar publicación
                </label>
                <input
                  type="datetime-local"
                  value={scheduleDate}
                  onChange={(e) => setScheduleDate(e.target.value)}
                  className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleSchedule}
                  disabled={saving || !scheduleDate}
                  className="mt-2 flex w-full items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  <Clock className="h-4 w-4" />
                  Programar
                </button>
              </div>
            )}

            {/* Validation errors */}
            {isEdit && post.publish_errors.length > 0 && (
              <div className="rounded-md bg-amber-50 px-3 py-2">
                <p className="text-xs font-medium text-amber-700 mb-1">Para publicar, corregir:</p>
                <ul className="text-xs text-amber-600 space-y-0.5">
                  {post.publish_errors.map((err, i) => (
                    <li key={i}>• {err}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Public visibility indicator */}
            {isEdit && (
              <div className={`rounded-md px-3 py-2 ${post.is_publicly_visible ? 'bg-emerald-50' : 'bg-slate-50'}`}>
                <p className={`text-xs font-medium ${post.is_publicly_visible ? 'text-emerald-700' : 'text-slate-500'}`}>
                  {post.is_publicly_visible
                    ? '✓ Visible públicamente en /blog'
                    : post.status === 'scheduled'
                      ? '⏱ Programado — será visible automáticamente'
                      : '○ No visible públicamente'}
                </p>
              </div>
            )}

            {/* Preview link */}
            {isEdit && post.preview_url && (
              <a
                href={post.preview_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm text-brand-600 hover:underline"
              >
                <Eye className="h-4 w-4" />
                {post.is_publicly_visible ? 'Ver en blog público' : 'Vista previa editorial'}
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        </SectionCard>

        {/* Category / Tags */}
        <SectionCard title="Categorización">
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Categoría</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              >
                <option value="">Sin categoría</option>
                {categories.map((cat) => (
                  <option key={cat.slug} value={cat.slug}>
                    {cat.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Tags</label>
              <input
                type="text"
                value={tagsStr}
                onChange={(e) => setTagsStr(e.target.value)}
                placeholder="inventario, excel, guía"
                className={inputClass}
              />
              <p className="mt-1 text-xs text-slate-400">Separados por coma.</p>
            </div>
          </div>
        </SectionCard>

        {/* Metadata */}
        {isEdit && (
          <SectionCard title="Metadata">
            <div className="space-y-2 text-sm text-slate-600">
              <div className="flex justify-between">
                <span className="text-slate-400">Creado:</span>
                <span>{formatDateTime(post.created_at)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Actualizado:</span>
                <span>{formatDateTime(post.updated_at)}</span>
              </div>
              {post.published_at && (
                <div className="flex justify-between">
                  <span className="text-slate-400">Publicado:</span>
                  <span>{formatDateTime(post.published_at)}</span>
                </div>
              )}
              {post.scheduled_publish_at && (
                <div className="flex justify-between">
                  <span className="text-slate-400">Programado:</span>
                  <span>{formatDateTime(post.scheduled_publish_at)}</span>
                </div>
              )}
              {post.author_name && (
                <div className="flex justify-between">
                  <span className="text-slate-400">Autor:</span>
                  <span>{post.author_name}</span>
                </div>
              )}
              {post.last_editor_name && (
                <div className="flex justify-between">
                  <span className="text-slate-400">Último editor:</span>
                  <span>{post.last_editor_name}</span>
                </div>
              )}
            </div>
          </SectionCard>
        )}
      </div>
    </div>
  );
}
