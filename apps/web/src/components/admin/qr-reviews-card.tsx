'use client';

import { useState, useEffect } from 'react';
import { Star, Globe, Building2, AlertTriangle, ExternalLink } from 'lucide-react';

import { SectionCard } from '@/components/admin/section-card';
import { apiGet, apiPatch } from '@/lib/api/client';
import type { AdminQRReviewsConfig, AdminQRReviewsConfigPatch } from '@/lib/admin/types';

// Slug validation: lowercase, digits and hyphens only.
const SLUG_RE = /^[a-z0-9-]+$/;

function validateSlug(value: string): string | null {
  const s = value.trim();
  if (!s) return 'El slug es obligatorio.';
  if (/\s/.test(s)) return 'El slug no puede contener espacios.';
  if (s.includes("'")) return 'El slug no puede contener apóstrofes.';
  if (!SLUG_RE.test(s)) return 'Solo letras minúsculas, números y guiones (-).';
  if (s.length > 80) return 'Máximo 80 caracteres.';
  return null;
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

type Props = {
  businessId: number;
};

export function QRResenasCard({ businessId }: Props) {
  const [config, setConfig] = useState<AdminQRReviewsConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  // Slug form state
  const [slugValue, setSlugValue] = useState('');
  const [slugError, setSlugError] = useState<string | null>(null);
  const [slugSave, setSlugSave] = useState<SaveState>('idle');
  const [slugServerError, setSlugServerError] = useState<string | null>(null);

  // Google Place form state
  const [placeId, setPlaceId] = useState('');
  const [placeName, setPlaceName] = useState('');
  const [placeAddress, setPlaceAddress] = useState('');
  const [reviewUrl, setReviewUrl] = useState('');
  const [customRedirectUrl, setCustomRedirectUrl] = useState('');
  const [placeSave, setPlaceSave] = useState<SaveState>('idle');
  const [placeServerError, setPlaceServerError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    apiGet<AdminQRReviewsConfig>(
      `/api/v1/platform-admin/clients/${businessId}/qr-reviews-config/`,
    )
      .then((data) => {
        setConfig(data);
        setSlugValue(data.business_slug);
        setPlaceId(data.google_place_id);
        setPlaceName(data.google_place_name);
        setPlaceAddress(data.google_place_formatted_address);
        setReviewUrl(data.google_review_url);
        setCustomRedirectUrl(data.custom_redirect_url);
      })
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  }, [businessId]);

  // Live slug preview
  const slugPreview = slugValue.trim()
    ? `https://www.mirubro.com/r/${slugValue.trim()}/`
    : '';

  async function handleSaveSlug() {
    const err = validateSlug(slugValue);
    if (err) {
      setSlugError(err);
      return;
    }
    setSlugError(null);
    setSlugServerError(null);
    setSlugSave('saving');
    try {
      const payload: AdminQRReviewsConfigPatch = { slug: slugValue.trim() };
      const updated = await apiPatch<AdminQRReviewsConfig>(
        `/api/v1/platform-admin/clients/${businessId}/qr-reviews-config/`,
        payload,
      );
      setConfig(updated);
      setSlugValue(updated.business_slug);
      setSlugSave('saved');
      setTimeout(() => setSlugSave('idle'), 3000);
    } catch (e: unknown) {
      const detail = e instanceof Error ? e.message : 'Error al guardar el slug.';
      setSlugServerError(detail);
      setSlugSave('error');
    }
  }

  async function handleSavePlace() {
    setPlaceServerError(null);
    setPlaceSave('saving');
    try {
      const payload: AdminQRReviewsConfigPatch = {
        google_place_id: placeId.trim(),
        google_place_name: placeName.trim(),
        google_place_formatted_address: placeAddress.trim(),
        google_review_url: reviewUrl.trim(),
        custom_redirect_url: customRedirectUrl.trim(),
      };
      const updated = await apiPatch<AdminQRReviewsConfig>(
        `/api/v1/platform-admin/clients/${businessId}/qr-reviews-config/`,
        payload,
      );
      setConfig(updated);
      setPlaceId(updated.google_place_id);
      setPlaceName(updated.google_place_name);
      setPlaceAddress(updated.google_place_formatted_address);
      setReviewUrl(updated.google_review_url);
      setCustomRedirectUrl(updated.custom_redirect_url);
      setPlaceSave('saved');
      setTimeout(() => setPlaceSave('idle'), 3000);
    } catch (e: unknown) {
      const detail = e instanceof Error ? e.message : 'Error al guardar.';
      setPlaceServerError(detail);
      setPlaceSave('error');
    }
  }

  if (loading) {
    return (
      <SectionCard title="QR de Reseñas" description="Configuración avanzada">
        <p className="text-sm text-slate-400">Cargando…</p>
      </SectionCard>
    );
  }

  if (loadError || !config) {
    return (
      <SectionCard title="QR de Reseñas" description="Configuración avanzada">
        <p className="text-sm text-red-500">No se pudo cargar la configuración.</p>
      </SectionCard>
    );
  }

  return (
    <SectionCard
      title="QR de Reseñas"
      description={`Business ID: ${config.business_id}`}
    >
      <div className="space-y-6">
        {/* ── Status summary ─────────────────────────────────── */}
        <div className="flex flex-wrap gap-3 text-xs">
          <span
            className={`rounded-full px-2.5 py-1 font-medium ${
              config.enabled
                ? 'bg-green-100 text-green-700'
                : 'bg-slate-100 text-slate-500'
            }`}
          >
            {config.enabled ? 'Habilitado' : 'Deshabilitado'}
          </span>
          <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">
            Modo: {config.mode === 'smart_filter' ? 'Filtro inteligente' : 'Directo'}
          </span>
          <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">
            Umbral: {config.redirect_threshold}★
          </span>
          {!config.review_config_exists && (
            <span className="rounded-full bg-amber-100 px-2.5 py-1 font-medium text-amber-700">
              Sin ReviewConfig — se creará al guardar
            </span>
          )}
        </div>

        {/* ── Section 1: URL pública / slug ────────────────── */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Globe className="h-4 w-4 text-slate-400" />
            <h4 className="text-sm font-semibold text-slate-700">URL pública</h4>
          </div>

          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <p className="text-xs text-amber-800">
                Cambiar el slug modifica la URL pública. Si ya se imprimieron QR con el
                slug anterior, podrían dejar de funcionar.
              </p>
            </div>
          </div>

          <div className="space-y-2">
            <label className="block text-xs font-medium text-slate-600">
              Slug actual
            </label>
            <div className="flex items-center gap-2">
              <span className="shrink-0 text-xs text-slate-400">mirubro.com/r/</span>
              <input
                type="text"
                value={slugValue}
                onChange={(e) => {
                  setSlugValue(e.target.value);
                  setSlugError(null);
                  setSlugServerError(null);
                  setSlugSave('idle');
                }}
                className="flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                placeholder="mi-negocio"
                spellCheck={false}
              />
            </div>

            {slugPreview && (
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-slate-400">Preview:</span>
                <a
                  href={slugPreview}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-brand-600 hover:underline"
                >
                  {slugPreview}
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            )}

            {(slugError || slugServerError) && (
              <p className="text-xs font-medium text-red-600">
                {slugError ?? slugServerError}
              </p>
            )}

            <button
              onClick={handleSaveSlug}
              disabled={slugSave === 'saving'}
              className="rounded-md bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {slugSave === 'saving'
                ? 'Guardando…'
                : slugSave === 'saved'
                ? '✓ Guardado'
                : 'Guardar slug'}
            </button>
          </div>
        </div>

        <hr className="border-slate-100" />

        {/* ── Section 2: Google Business ───────────────────── */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Building2 className="h-4 w-4 text-slate-400" />
            <h4 className="text-sm font-semibold text-slate-700">Google Business</h4>
          </div>

          {config.google_place_updated_at && (
            <p className="text-xs text-slate-400">
              Última actualización de lugar:{' '}
              {new Date(config.google_place_updated_at).toLocaleString('es-AR')}
            </p>
          )}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Google Place ID
              </label>
              <input
                type="text"
                value={placeId}
                onChange={(e) => { setPlaceId(e.target.value); setPlaceSave('idle'); setPlaceServerError(null); }}
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                placeholder="ChIJ..."
                spellCheck={false}
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Nombre del lugar
              </label>
              <input
                type="text"
                value={placeName}
                onChange={(e) => { setPlaceName(e.target.value); setPlaceSave('idle'); }}
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                placeholder="Nombre del negocio en Google"
              />
            </div>

            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Dirección formateada
              </label>
              <input
                type="text"
                value={placeAddress}
                onChange={(e) => { setPlaceAddress(e.target.value); setPlaceSave('idle'); }}
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                placeholder="Av. Corrientes 1234, Buenos Aires"
              />
            </div>

            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Google review URL
              </label>
              <input
                type="url"
                value={reviewUrl}
                onChange={(e) => { setReviewUrl(e.target.value); setPlaceSave('idle'); }}
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                placeholder="https://search.google.com/local/writereview?placeid=..."
              />
            </div>

            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-medium text-slate-600">
                URL de redirección personalizada
              </label>
              <input
                type="url"
                value={customRedirectUrl}
                onChange={(e) => { setCustomRedirectUrl(e.target.value); setPlaceSave('idle'); }}
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                placeholder="https://g.page/mi-negocio/review"
              />
            </div>
          </div>

          {placeServerError && (
            <p className="text-xs font-medium text-red-600">{placeServerError}</p>
          )}

          <button
            onClick={handleSavePlace}
            disabled={placeSave === 'saving'}
            className="rounded-md bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {placeSave === 'saving'
              ? 'Guardando…'
              : placeSave === 'saved'
              ? '✓ Guardado'
              : 'Guardar configuración'}
          </button>
        </div>
      </div>
    </SectionCard>
  );
}
