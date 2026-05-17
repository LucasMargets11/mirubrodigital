'use client';

import { useRef, useState } from 'react';

import { POSTER_SIZES, POSTER_TEMPLATES, BACKGROUND_COLORS, TEXT_COLOR_PALETTE, OUTLINE_COLOR_PALETTE, OUTLINE_WIDTH_OPTIONS, TEXT_SPACING_OPTIONS, UPPERCASE_OPTIONS, QR_VERTICAL_ALIGN_OPTIONS, QR_SIZE_MM_PRESETS, QR_SIZE_MM_MIN, QR_SIZE_MM_MAX, QR_BOTTOM_OFFSET_MM_MIN, QR_BOTTOM_OFFSET_MM_MAX, QR_BOTTOM_OFFSET_MM_DEFAULT, resolveQrSizeMm, POSTER_FONT_FAMILIES, getPosterFontFamily, resolvePosterFontWeight, LOGO_VARIANT_OPTIONS, LOGO_POSITION_OPTIONS, LOGO_MARGIN_MM_MIN, LOGO_MARGIN_MM_MAX, LOGO_MARGIN_MM_DEFAULT } from '../constants';
import { useGenerateQrPosterPdf } from '../hooks';
import type { GenerateQrPosterPayload, PosterFontFamily } from '../types';
import { useBusinessBrandingQuery } from '@/features/business/branding/hooks';

interface Props {
    payload: GenerateQrPosterPayload;
    onChange: (patch: Partial<GenerateQrPosterPayload>) => void;
}

export function QrPosterEditor({ payload, onChange }: Props) {
    const { generate, isLoading, error, clearError } = useGenerateQrPosterPdf();
    const [fileError, setFileError] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement | null>(null);
    const brandingQuery = useBusinessBrandingQuery();
    const hasLogo = !!(brandingQuery.data?.logo_horizontal_url || brandingQuery.data?.logo_square_url);
    const showNoLogoWarning = payload.include_logo && !brandingQuery.isPending && !hasLogo;

    // Warning when the specifically-chosen logo variant has no URL loaded
    const missingLogoWarning = payload.logo_variant !== 'none' && !brandingQuery.isPending && (
        (payload.logo_variant === 'horizontal' && !brandingQuery.data?.logo_horizontal_url) ||
        (payload.logo_variant === 'square' && !brandingQuery.data?.logo_square_url) ||
        (payload.logo_variant === 'default' && !brandingQuery.data?.logo_horizontal_url && !brandingQuery.data?.logo_square_url)
    );

    function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
        const file = e.target.files?.[0];
        // Reset value so the same file can be re-selected later
        e.currentTarget.value = '';
        if (!file) return;
        if (file.size > 10 * 1024 * 1024) {
            setFileError('La imagen no puede superar 10 MB.');
            return;
        }
        const name = file.name.toLowerCase();
        if (!name.endsWith('.jpg') && !name.endsWith('.jpeg') && !name.endsWith('.png')) {
            setFileError('Solo se aceptan JPG o PNG.');
            return;
        }
        setFileError(null);
        onChange({ background_image: file });
    }

    function handleGenerate() {
        clearError();
        void generate(payload);
    }

    return (
        <div className="space-y-5">

            {/* ── Tamaño ─────────────────────────────────────────────────────── */}
            <section className="space-y-2">
                <label className="text-sm font-medium text-slate-700">Tamaño</label>
                <div className="grid grid-cols-3 gap-2">
                    {POSTER_SIZES.map((s) => (
                        <button
                            key={s.code}
                            type="button"
                            onClick={() => onChange({ poster_size: s.code })}
                            className={[
                                'rounded-lg border px-2 py-2 text-center transition-colors',
                                payload.poster_size === s.code
                                    ? 'border-slate-900 bg-slate-900 text-white'
                                    : 'border-slate-200 bg-white text-slate-700 hover:border-slate-400',
                            ].join(' ')}
                        >
                            <span className="block text-xs font-medium leading-tight">{s.label}</span>
                            <span className="mt-0.5 block text-[10px] opacity-70">{s.description}</span>
                        </button>
                    ))}
                </div>
            </section>

            {/* ── Diseño ─────────────────────────────────────────────────────── */}
            <section className="space-y-2">
                <label className="text-sm font-medium text-slate-700">Diseño</label>
                <div className="space-y-2">
                    {POSTER_TEMPLATES.map((t) => (
                        <button
                            key={t.code}
                            type="button"
                            onClick={() => onChange({ template_code: t.code })}
                            className={[
                                'flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors',
                                payload.template_code === t.code
                                    ? 'border-slate-900 bg-slate-900 text-white'
                                    : 'border-slate-200 bg-white text-slate-700 hover:border-slate-400',
                            ].join(' ')}
                        >
                            <div className="flex-1">
                                <p className="text-sm font-medium">{t.label}</p>
                                <p
                                    className={[
                                        'text-xs',
                                        payload.template_code === t.code
                                            ? 'text-slate-300'
                                            : 'text-slate-500',
                                    ].join(' ')}
                                >
                                    {t.description}
                                </p>
                            </div>
                            {payload.template_code === t.code && (
                                <svg
                                    className="h-4 w-4 shrink-0"
                                    fill="currentColor"
                                    viewBox="0 0 20 20"
                                    aria-hidden="true"
                                >
                                    <path
                                        fillRule="evenodd"
                                        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                                        clipRule="evenodd"
                                    />
                                </svg>
                            )}
                        </button>
                    ))}
                </div>
            </section>

            {/* ── Texto principal ────────────────────────────────────────────── */}
            <section className="space-y-1.5">
                <label htmlFor="poster-main-text" className="text-sm font-medium text-slate-700">
                    Texto principal
                </label>
                <input
                    id="poster-main-text"
                    type="text"
                    value={payload.main_text}
                    maxLength={80}
                    onChange={(e) => onChange({ main_text: e.target.value })}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200"
                />
                <p className="text-right text-xs text-slate-400">
                    {payload.main_text.length}/80
                </p>
            </section>

            {/* ── Subtítulo ──────────────────────────────────────────────────── */}
            <section className="space-y-1.5">
                <label htmlFor="poster-subtitle" className="text-sm font-medium text-slate-700">
                    Subtítulo{' '}
                    <span className="font-normal text-slate-400">(opcional)</span>
                </label>
                <input
                    id="poster-subtitle"
                    type="text"
                    value={payload.subtitle ?? ''}
                    onChange={(e) => onChange({ subtitle: e.target.value })}
                    placeholder="Tu reseña nos ayuda a mejorar"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200"
                />
            </section>

            {/* ── Texto y estilo ──────────────────────────────────────────────── */}
            <section className="space-y-3">
                <label className="text-sm font-medium text-slate-700">Texto y estilo</label>

                {/* Tipografía — nueva selección avanzada */}
                <div className="space-y-2">
                    <p className="text-xs text-slate-500">Tipografía</p>
                    <div className="grid grid-cols-2 gap-1.5">
                        {POSTER_FONT_FAMILIES.map((f) => {
                            const isSelected = (payload.font_family ?? 'montserrat') === f.id;
                            return (
                                <button
                                    key={f.id}
                                    type="button"
                                    onClick={() => {
                                        const currentWeight = payload.font_weight ?? 'bold';
                                        const hasWeight = f.weights.some((w) => w.id === currentWeight);
                                        onChange({
                                            font_family: f.id as PosterFontFamily,
                                            font_weight: hasWeight ? currentWeight : (f.weights.find((w) => w.id === 'bold')?.id ?? f.weights[0].id),
                                        });
                                    }}
                                    className={[
                                        'flex flex-col rounded-lg border px-2.5 py-2 text-left transition-colors',
                                        isSelected
                                            ? 'border-slate-900 bg-slate-900 text-white'
                                            : 'border-slate-200 bg-white text-slate-700 hover:border-slate-400',
                                    ].join(' ')}
                                >
                                    <span
                                        className="block text-sm font-semibold leading-tight"
                                        style={{ fontFamily: f.cssFamily }}
                                    >
                                        {f.label}
                                    </span>
                                    <span
                                        className={[
                                            'mt-0.5 block text-[10px]',
                                            isSelected ? 'text-slate-300' : 'text-slate-400',
                                        ].join(' ')}
                                    >
                                        {f.category}
                                    </span>
                                </button>
                            );
                        })}
                    </div>
                </div>

                {/* Peso de la tipografía seleccionada */}
                {(() => {
                    const activeFamilyId = payload.font_family ?? 'montserrat';
                    const activeFamily = getPosterFontFamily(activeFamilyId as PosterFontFamily);
                    if (!activeFamily) return null;
                    const currentWeight = resolvePosterFontWeight(activeFamily, payload.font_weight);
                    return (
                        <div className="space-y-1.5">
                            <p className="text-xs text-slate-500">Estilo</p>
                            <div className="flex gap-2">
                                {activeFamily.weights.map((w) => (
                                    <button
                                        key={w.id}
                                        type="button"
                                        onClick={() => onChange({ font_weight: w.id })}
                                        className={[
                                            'flex-1 rounded-lg border px-3 py-2 text-center text-xs transition-colors',
                                            currentWeight.id === w.id
                                                ? 'border-slate-900 bg-slate-900 text-white font-semibold'
                                                : 'border-slate-200 bg-white text-slate-700 hover:border-slate-400',
                                        ].join(' ')}
                                        style={{ fontFamily: activeFamily.cssFamily, fontWeight: w.cssWeight }}
                                    >
                                        {w.label}
                                    </button>
                                ))}
                            </div>
                        </div>
                    );
                })()}

                {/* Color del título */}
                <div className="space-y-1.5">
                    <p className="text-xs text-slate-500">Color del título</p>
                    <div className="flex flex-wrap gap-2">
                        <button
                            type="button"
                            title="Automático"
                            onClick={() => onChange({ main_text_color: null })}
                            aria-label="Automático"
                            aria-pressed={payload.main_text_color == null}
                            className={[
                                'flex h-8 w-8 items-center justify-center rounded-full border-2 text-[10px] font-bold transition-all',
                                payload.main_text_color == null
                                    ? 'border-slate-900 bg-slate-100 text-slate-700 scale-110'
                                    : 'border-slate-200 bg-slate-50 text-slate-400 hover:scale-105',
                            ].join(' ')}
                        >
                            A
                        </button>
                        {TEXT_COLOR_PALETTE.map((c) => (
                            <button
                                key={c.hex}
                                type="button"
                                title={c.name}
                                onClick={() => onChange({ main_text_color: c.hex })}
                                style={{ backgroundColor: c.hex }}
                                aria-label={c.name}
                                aria-pressed={payload.main_text_color === c.hex}
                                className={[
                                    'h-8 w-8 rounded-full border-2 transition-all',
                                    payload.main_text_color === c.hex
                                        ? 'border-slate-900 ring-2 ring-slate-300 scale-110'
                                        : 'border-slate-200 hover:scale-105',
                                ].join(' ')}
                            />
                        ))}
                    </div>
                </div>

                {/* Color del subtítulo */}
                <div className="space-y-1.5">
                    <p className="text-xs text-slate-500">Color del subtítulo</p>
                    <div className="flex flex-wrap gap-2">
                        <button
                            type="button"
                            title="Automático"
                            onClick={() => onChange({ subtitle_text_color: null })}
                            aria-label="Automático"
                            aria-pressed={payload.subtitle_text_color == null}
                            className={[
                                'flex h-8 w-8 items-center justify-center rounded-full border-2 text-[10px] font-bold transition-all',
                                payload.subtitle_text_color == null
                                    ? 'border-slate-900 bg-slate-100 text-slate-700 scale-110'
                                    : 'border-slate-200 bg-slate-50 text-slate-400 hover:scale-105',
                            ].join(' ')}
                        >
                            A
                        </button>
                        {TEXT_COLOR_PALETTE.map((c) => (
                            <button
                                key={c.hex}
                                type="button"
                                title={c.name}
                                onClick={() => onChange({ subtitle_text_color: c.hex })}
                                style={{ backgroundColor: c.hex }}
                                aria-label={c.name}
                                aria-pressed={payload.subtitle_text_color === c.hex}
                                className={[
                                    'h-8 w-8 rounded-full border-2 transition-all',
                                    payload.subtitle_text_color === c.hex
                                        ? 'border-slate-900 ring-2 ring-slate-300 scale-110'
                                        : 'border-slate-200 hover:scale-105',
                                ].join(' ')}
                            />
                        ))}
                    </div>
                </div>
            </section>

            {/* ── Borde de letra ─────────────────────────────────────────────── */}
            <section className="space-y-3">
                <label className="text-sm font-medium text-slate-700">Borde de letra</label>

                {/* Borde en título */}
                <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                        <p className="text-xs text-slate-500">Borde en título</p>
                        <button
                            type="button"
                            role="switch"
                            aria-checked={payload.main_text_outline_enabled}
                            onClick={() => onChange({ main_text_outline_enabled: !payload.main_text_outline_enabled })}
                            className={[
                                'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors',
                                payload.main_text_outline_enabled ? 'bg-slate-900' : 'bg-slate-200',
                            ].join(' ')}
                        >
                            <span
                                className={[
                                    'pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform',
                                    payload.main_text_outline_enabled ? 'translate-x-4' : 'translate-x-0',
                                ].join(' ')}
                            />
                        </button>
                    </div>
                    {payload.main_text_outline_enabled && (
                        <div className="flex flex-wrap gap-2">
                            {OUTLINE_COLOR_PALETTE.map((c) => (
                                <button
                                    key={c.hex}
                                    type="button"
                                    title={c.name}
                                    onClick={() => onChange({ main_text_outline_color: c.hex })}
                                    style={{ backgroundColor: c.hex }}
                                    aria-label={c.name}
                                    aria-pressed={payload.main_text_outline_color === c.hex}
                                    className={[
                                        'h-8 w-8 rounded-full border-2 transition-all',
                                        payload.main_text_outline_color === c.hex
                                            ? 'border-slate-900 ring-2 ring-slate-300 scale-110'
                                            : 'border-slate-200 hover:scale-105',
                                    ].join(' ')}
                                />
                            ))}
                        </div>
                    )}
                </div>

                {/* Borde en subtítulo */}
                <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                        <p className="text-xs text-slate-500">Borde en subtítulo</p>
                        <button
                            type="button"
                            role="switch"
                            aria-checked={payload.subtitle_text_outline_enabled}
                            onClick={() => onChange({ subtitle_text_outline_enabled: !payload.subtitle_text_outline_enabled })}
                            className={[
                                'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors',
                                payload.subtitle_text_outline_enabled ? 'bg-slate-900' : 'bg-slate-200',
                            ].join(' ')}
                        >
                            <span
                                className={[
                                    'pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform',
                                    payload.subtitle_text_outline_enabled ? 'translate-x-4' : 'translate-x-0',
                                ].join(' ')}
                            />
                        </button>
                    </div>
                    {payload.subtitle_text_outline_enabled && (
                        <div className="flex flex-wrap gap-2">
                            {OUTLINE_COLOR_PALETTE.map((c) => (
                                <button
                                    key={c.hex}
                                    type="button"
                                    title={c.name}
                                    onClick={() => onChange({ subtitle_text_outline_color: c.hex })}
                                    style={{ backgroundColor: c.hex }}
                                    aria-label={c.name}
                                    aria-pressed={payload.subtitle_text_outline_color === c.hex}
                                    className={[
                                        'h-8 w-8 rounded-full border-2 transition-all',
                                        payload.subtitle_text_outline_color === c.hex
                                            ? 'border-slate-900 ring-2 ring-slate-300 scale-110'
                                            : 'border-slate-200 hover:scale-105',
                                    ].join(' ')}
                                />
                            ))}
                        </div>
                    )}
                </div>

                {/* Grosor compartido — solo visible si al menos un borde está activo */}
                {(payload.main_text_outline_enabled || payload.subtitle_text_outline_enabled) && (
                    <div className="space-y-1.5">
                        <p className="text-xs text-slate-500">Grosor del borde</p>
                        <div className="grid grid-cols-4 gap-1.5">
                            {OUTLINE_WIDTH_OPTIONS.map((o) => (
                                <button
                                    key={o.value}
                                    type="button"
                                    onClick={() => onChange({ text_outline_width: o.value })}
                                    className={[
                                        'rounded-lg border px-1 py-2 text-center text-xs font-medium transition-colors',
                                        payload.text_outline_width === o.value
                                            ? 'border-slate-900 bg-slate-900 text-white'
                                            : 'border-slate-200 bg-white text-slate-700 hover:border-slate-400',
                                    ].join(' ')}
                                >
                                    {o.label}
                                </button>
                            ))}
                        </div>
                    </div>
                )}
            </section>

            {/* QR — posición y tamaño */}
            <section className="space-y-4">
                <label className="text-sm font-medium text-slate-700">Posición y tamaño del QR</label>

                {/* Posición vertical */}
                <div className="space-y-1.5">
                    <p className="text-xs text-slate-500">Posición vertical</p>
                    <div className="grid grid-cols-3 gap-1.5">
                        {QR_VERTICAL_ALIGN_OPTIONS.map((o) => (
                            <button
                                key={o.value}
                                type="button"
                                onClick={() => onChange({ qr_vertical_align: o.value })}
                                className={[
                                    'rounded-lg border px-2 py-2 text-center text-xs font-medium transition-colors',
                                    (payload.qr_vertical_align ?? 'center') === o.value
                                        ? 'border-slate-900 bg-slate-900 text-white'
                                        : 'border-slate-200 bg-white text-slate-700 hover:border-slate-400',
                                ].join(' ')}
                            >
                                {o.label}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Tamaño del QR — presets + slider */}
                <div className="space-y-2">
                    <p className="text-xs text-slate-500">Tamaño del QR</p>
                    {/* Presets */}
                    <div className="grid grid-cols-3 gap-1.5">
                        {QR_SIZE_MM_PRESETS.map((p) => (
                            <button
                                key={p.value}
                                type="button"
                                onClick={() => onChange({ qr_size_mm: p.value })}
                                className={[
                                    'rounded-lg border px-2 py-2 text-center text-xs font-medium transition-colors',
                                    resolveQrSizeMm(payload) === p.value
                                        ? 'border-slate-900 bg-slate-900 text-white'
                                        : 'border-slate-200 bg-white text-slate-700 hover:border-slate-400',
                                ].join(' ')}
                            >
                                {p.label}
                            </button>
                        ))}
                    </div>
                    {/* Slider */}
                    <div className="space-y-1">
                        <div className="flex items-center justify-between">
                            <span className="text-[10px] text-slate-400">{QR_SIZE_MM_MIN} mm</span>
                            <span className="text-xs font-medium text-slate-700">
                                {resolveQrSizeMm(payload)} mm
                            </span>
                            <span className="text-[10px] text-slate-400">{QR_SIZE_MM_MAX} mm</span>
                        </div>
                        <input
                            type="range"
                            min={QR_SIZE_MM_MIN}
                            max={QR_SIZE_MM_MAX}
                            step={1}
                            value={resolveQrSizeMm(payload)}
                            onChange={(e) => onChange({ qr_size_mm: Number(e.target.value) })}
                            className="w-full accent-slate-900"
                            aria-label="Tamaño del QR en mm"
                        />
                    </div>
                </div>

                {/* Separación inferior — siempre visible, destacada cuando posición = Abajo */}
                <div className={[
                    'space-y-2 rounded-lg border p-3 transition-colors',
                    (payload.qr_vertical_align ?? 'center') === 'bottom'
                        ? 'border-slate-400 bg-slate-50'
                        : 'border-slate-100 bg-white',
                ].join(' ')}>
                    <div className="flex items-center justify-between">
                        <p className="text-xs font-medium text-slate-600">
                            Separación inferior{' '}
                            {(payload.qr_vertical_align ?? 'center') === 'bottom' && (
                                <span className="ml-1 rounded-full bg-slate-900 px-1.5 py-0.5 text-[9px] font-semibold text-white">
                                    activa
                                </span>
                            )}
                        </p>
                        <span className="text-xs font-medium text-slate-700">
                            {payload.qr_bottom_offset_mm ?? QR_BOTTOM_OFFSET_MM_DEFAULT} mm
                        </span>
                    </div>
                    <input
                        type="range"
                        min={QR_BOTTOM_OFFSET_MM_MIN}
                        max={QR_BOTTOM_OFFSET_MM_MAX}
                        step={1}
                        value={payload.qr_bottom_offset_mm ?? QR_BOTTOM_OFFSET_MM_DEFAULT}
                        onChange={(e) => onChange({ qr_bottom_offset_mm: Number(e.target.value) })}
                        className="w-full accent-slate-900"
                        aria-label="Separación inferior del QR en mm"
                    />
                    <div className="flex justify-between">
                        <span className="text-[10px] text-slate-400">{QR_BOTTOM_OFFSET_MM_MIN} mm</span>
                        <span className="text-[10px] text-slate-400">{QR_BOTTOM_OFFSET_MM_MAX} mm</span>
                    </div>
                    <p className="text-[10px] text-slate-400">
                        Define cuánto espacio queda entre el QR y el borde inferior del cartel.
                    </p>
                </div>

            </section>

            {/* QR y espaciado */}
            <section className="space-y-3">
                <label className="text-sm font-medium text-slate-700">Espaciado de texto</label>

                {/* Separación */}
                <div className="space-y-1.5">
                    <p className="text-xs text-slate-500">Separación título / subtítulo</p>
                    <div className="grid grid-cols-3 gap-1.5">
                        {TEXT_SPACING_OPTIONS.map((o) => (
                            <button
                                key={o.value}
                                type="button"
                                onClick={() => onChange({ text_spacing: o.value })}
                                className={[
                                    'rounded-lg border px-2 py-2 text-center text-xs font-medium transition-colors',
                                    (payload.text_spacing ?? 'normal') === o.value
                                        ? 'border-slate-900 bg-slate-900 text-white'
                                        : 'border-slate-200 bg-white text-slate-700 hover:border-slate-400',
                                ].join(' ')}
                            >
                                {o.label}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Mayúsculas */}
                <div className="space-y-1.5">
                    <p className="text-xs text-slate-500">Mayúsculas</p>
                    <div className="grid grid-cols-3 gap-1.5">
                        {UPPERCASE_OPTIONS.map((o) => (
                            <button
                                key={o.value}
                                type="button"
                                onClick={() => onChange({ uppercase_mode: o.value })}
                                className={[
                                    'rounded-lg border px-2 py-2 text-center text-xs font-medium transition-colors',
                                    (payload.uppercase_mode ?? 'none') === o.value
                                        ? 'border-slate-900 bg-slate-900 text-white'
                                        : 'border-slate-200 bg-white text-slate-700 hover:border-slate-400',
                                ].join(' ')}
                            >
                                {o.label}
                            </button>
                        ))}
                    </div>
                </div>
            </section>

            {/* Fondo */}
            <section className="space-y-2">
                <label className="text-sm font-medium text-slate-700">Fondo</label>

                {/* Selector de modo */}
                <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-1">
                    {(['color', 'image'] as const).map((mode) => (
                        <button
                            key={mode}
                            type="button"
                            onClick={() => {
                                if (mode === 'color') {
                                    onChange({ background_mode: 'color', background_image: null });
                                    setFileError(null);
                                } else {
                                    onChange({ background_mode: 'image' });
                                }
                            }}
                            className={[
                                'flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                                payload.background_mode === mode
                                    ? 'bg-white text-slate-800 shadow-sm'
                                    : 'text-slate-500 hover:text-slate-700',
                            ].join(' ')}
                        >
                            {mode === 'color' ? 'Color sólido' : 'Imagen'}
                        </button>
                    ))}
                </div>

                {/* Paleta de colores */}
                {payload.background_mode === 'color' && (
                    <div className="flex flex-wrap gap-2.5">
                        {BACKGROUND_COLORS.map((c) => (
                            <button
                                key={c.hex}
                                type="button"
                                title={c.name}
                                onClick={() => onChange({ background_color: c.hex })}
                                style={{ backgroundColor: c.hex }}
                                aria-label={c.name}
                                aria-pressed={payload.background_color === c.hex}
                                className={[
                                    'h-8 w-8 rounded-full border-2 transition-all',
                                    payload.background_color === c.hex
                                        ? 'border-brand-600 ring-2 ring-brand-300 scale-110'
                                        : 'border-slate-200 hover:scale-105',
                                ].join(' ')}
                            />
                        ))}
                    </div>
                )}

                {/* Carga de imagen */}
                {payload.background_mode === 'image' && (
                    <div className="space-y-1.5">
                        {payload.background_image ? (
                            <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                                <svg
                                    className="h-4 w-4 shrink-0 text-slate-400"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    stroke="currentColor"
                                    strokeWidth={2}
                                    aria-hidden="true"
                                >
                                    <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                                    />
                                </svg>
                                <span className="min-w-0 flex-1 truncate text-xs text-slate-700">
                                    {payload.background_image.name}
                                </span>
                                <button
                                    type="button"
                                    onClick={() => {
                                        onChange({ background_image: null });
                                        setFileError(null);
                                    }}
                                    className="shrink-0 text-slate-400 transition-colors hover:text-red-500"
                                    aria-label="Quitar imagen"
                                >
                                    <svg
                                        className="h-4 w-4"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        stroke="currentColor"
                                        strokeWidth={2}
                                        aria-hidden="true"
                                    >
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            d="M6 18L18 6M6 6l12 12"
                                        />
                                    </svg>
                                </button>
                            </div>
                        ) : (
                            <div className="space-y-1.5">
                                <button
                                    type="button"
                                    onClick={() => fileInputRef.current?.click()}
                                    className="block w-full cursor-pointer rounded-lg border-2 border-dashed border-slate-200 bg-slate-50 px-4 py-4 text-center transition-colors hover:border-slate-400 hover:bg-slate-100"
                                >
                                    <svg
                                        className="mx-auto mb-1.5 h-5 w-5 text-slate-400"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        stroke="currentColor"
                                        strokeWidth={1.5}
                                        aria-hidden="true"
                                    >
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
                                        />
                                    </svg>
                                    <p className="text-xs font-medium text-slate-600">Elegir imagen</p>
                                    <p className="mt-0.5 text-[10px] text-slate-400">JPG o PNG · máx. 10 MB</p>
                                </button>
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    accept=".jpg,.jpeg,.png"
                                    className="hidden"
                                    tabIndex={-1}
                                    onChange={handleFileChange}
                                />
                            </div>
                        )}
                        {fileError && (
                            <p className="text-xs text-red-600">{fileError}</p>
                        )}
                    </div>
                )}
            </section>

            {/* ── Logo del negocio ───────────────────────────────────────────── */}
            <section className="space-y-3">
                <label className="text-sm font-medium text-slate-700">Logo del negocio</label>

                {/* Variante: sin logo / horizontal / cuadrado */}
                <div className="grid grid-cols-3 gap-1.5">
                    {LOGO_VARIANT_OPTIONS.map((opt) => (
                        <button
                            key={opt.value}
                            type="button"
                            onClick={() => onChange({
                                logo_variant: opt.value,
                                include_logo: opt.value !== 'none',
                            })}
                            className={[
                                'rounded-lg border px-2 py-2 text-center text-xs font-medium transition-colors',
                                payload.logo_variant === opt.value
                                    ? 'border-slate-900 bg-slate-900 text-white'
                                    : 'border-slate-200 bg-white text-slate-700 hover:border-slate-400',
                            ].join(' ')}
                        >
                            {opt.label}
                        </button>
                    ))}
                </div>

                {/* Posición y margen — solo cuando hay logo */}
                {payload.logo_variant !== 'none' && (
                    <>
                        {/* Warning: logo de la variante elegida no cargado */}
                        {missingLogoWarning && (
                            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800">
                                No tenés este logo cargado todavía.{' '}
                                <a
                                    href="/app/resenas/configuracion#marca"
                                    className="font-semibold underline hover:text-amber-900"
                                >
                                    Configurar marca del negocio
                                </a>
                            </div>
                        )}

                        {/* Posición: grilla 3×2 + fila de 2 laterales */}
                        <div className="space-y-1.5">
                            <p className="text-xs text-slate-500">Posición</p>
                            <div className="grid grid-cols-3 gap-1.5">
                                {LOGO_POSITION_OPTIONS.filter((o) => !o.value.startsWith('middle')).map((opt) => (
                                    <button
                                        key={opt.value}
                                        type="button"
                                        onClick={() => onChange({ logo_position: opt.value })}
                                        className={[
                                            'rounded-lg border px-1.5 py-1.5 text-center text-[10px] font-medium transition-colors leading-tight',
                                            (payload.logo_position ?? 'top-center') === opt.value
                                                ? 'border-slate-900 bg-slate-900 text-white'
                                                : 'border-slate-200 bg-white text-slate-600 hover:border-slate-400',
                                        ].join(' ')}
                                    >
                                        {opt.label}
                                    </button>
                                ))}
                            </div>
                            <div className="grid grid-cols-2 gap-1.5">
                                {LOGO_POSITION_OPTIONS.filter((o) => o.value.startsWith('middle')).map((opt) => (
                                    <button
                                        key={opt.value}
                                        type="button"
                                        onClick={() => onChange({ logo_position: opt.value })}
                                        className={[
                                            'rounded-lg border px-1.5 py-1.5 text-center text-[10px] font-medium transition-colors leading-tight',
                                            (payload.logo_position ?? 'top-center') === opt.value
                                                ? 'border-slate-900 bg-slate-900 text-white'
                                                : 'border-slate-200 bg-white text-slate-600 hover:border-slate-400',
                                        ].join(' ')}
                                    >
                                        {opt.label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Margen */}
                        <div className="space-y-1">
                            <div className="flex items-center justify-between">
                                <p className="text-xs text-slate-500">Margen del logo</p>
                                <span className="text-xs font-medium text-slate-700">
                                    {payload.logo_margin_mm ?? LOGO_MARGIN_MM_DEFAULT} mm
                                </span>
                            </div>
                            <input
                                type="range"
                                min={LOGO_MARGIN_MM_MIN}
                                max={LOGO_MARGIN_MM_MAX}
                                step={1}
                                value={payload.logo_margin_mm ?? LOGO_MARGIN_MM_DEFAULT}
                                onChange={(e) => onChange({ logo_margin_mm: Number(e.target.value) })}
                                className="w-full accent-slate-900"
                            />
                            <div className="flex justify-between">
                                <span className="text-[10px] text-slate-400">{LOGO_MARGIN_MM_MIN} mm</span>
                                <span className="text-[10px] text-slate-400">{LOGO_MARGIN_MM_MAX} mm</span>
                            </div>
                        </div>
                    </>
                )}
            </section>

            {/* ── Error ──────────────────────────────────────────────────────── */}
            {error && (
                <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
                    {error}
                </p>
            )}

            {/* ── Descargar PDF ──────────────────────────────────────────────── */}
            <button
                type="button"
                onClick={handleGenerate}
                disabled={isLoading || !payload.main_text.trim() || (payload.background_mode === 'image' && !payload.background_image)}
                className="w-full rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
                {isLoading ? 'Generando PDF…' : 'Descargar cartel PDF'}
            </button>
        </div>
    );
}
