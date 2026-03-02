"use client";

import { useEffect, useState, useCallback } from "react";
import { MenuCategory, MenuConfig } from "./types";
import { MenuCategorySection } from "./category-section";
import { MenuBrandHeader } from "./brand-header";
import { getMenuFontFamily } from "@/lib/fonts";
import { buildMediaUrl } from "@/lib/api-url";
import type { PublicMenuEngagement, PublicMenuLayoutBlock } from "@/features/menu/types";
import { createPublicTipPreference } from "@/features/menu/api";

// ─── Types ────────────────────────────────────────────────────────────────────
interface PublicMenuLayoutProps {
    config: MenuConfig;
    categories: MenuCategory[];
    layoutBlocks?: PublicMenuLayoutBlock[];
    engagement?: PublicMenuEngagement | null;
    slug?: string;
}

// ─── QR Modal ─────────────────────────────────────────────────────────────────
function QRModal({
    open,
    onClose,
    qrImageUrl,
    mpTipUrl,
    accentColor,
}: {
    open: boolean;
    onClose: () => void;
    qrImageUrl: string;
    mpTipUrl?: string | null;
    accentColor: string;
}) {
    useEffect(() => {
        if (!open) return;
        const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
        window.addEventListener('keydown', handleKey);
        return () => window.removeEventListener('keydown', handleKey);
    }, [open, onClose]);

    if (!open) return null;

    return (
        <div
            className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
            role="dialog"
            aria-modal="true"
            aria-label="Código QR para propina"
        >
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/60 backdrop-blur-sm"
                onClick={onClose}
                aria-hidden="true"
            />
            {/* Modal card */}
            <div className="relative z-10 w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl text-center space-y-4">
                <button
                    className="absolute top-3 right-3 rounded-full p-1.5 text-slate-400 hover:bg-slate-100 transition-colors"
                    onClick={onClose}
                    aria-label="Cerrar"
                >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>

                <div>
                    <p className="text-base font-bold text-slate-800">Dejá tu propina</p>
                    <p className="text-xs text-slate-500 mt-1">Escaneá el código con la app de Mercado Pago</p>
                </div>

                <div className="flex justify-center">
                    <img
                        src={qrImageUrl}
                        alt="Código QR Mercado Pago"
                        className="h-48 w-48 rounded-xl border object-contain bg-white p-2"
                    />
                </div>

                {mpTipUrl ? (
                    <a
                        href={mpTipUrl}
                        target={typeof window !== 'undefined' && window.innerWidth >= 768 ? '_blank' : '_self'}
                        rel="noopener noreferrer"
                        className="flex w-full items-center justify-center gap-2 rounded-xl py-3 px-4 text-sm font-semibold text-white transition-opacity hover:opacity-90 active:opacity-80"
                        style={{ backgroundColor: '#009ee3' }}
                    >
                        Abrir Mercado Pago
                    </a>
                ) : (
                    <p className="text-xs text-slate-400">Abrí la app de Mercado Pago y escaneá el código</p>
                )}
            </div>
        </div>
    );
}

// ─── Tip Amount Selector (Fase 2 — MP OAuth Checkout) ─────────────────────────
const TIP_PRESETS = [500, 1000, 1500, 2000];

function TipAmountSelector({
    slug,
    accentColor,
    open,
    onClose,
}: {
    slug: string;
    accentColor: string;
    open: boolean;
    onClose: () => void;
}) {
    const [selected, setSelected] = useState<number | null>(null);
    const [custom, setCustom] = useState('');
    const [loading, setLoading] = useState(false);
    const [err, setErr] = useState<string | null>(null);

    const amount = selected ?? (custom ? parseFloat(custom) : null);

    if (!open) return null;

    async function handleConfirm() {
        if (!amount || amount < 10) { setErr('El monto mínimo es $10.'); return; }
        setLoading(true);
        setErr(null);
        try {
            const { init_point } = await createPublicTipPreference(slug, amount);
            window.location.href = init_point;
        } catch (e: any) {
            setErr(e?.payload?.detail ?? 'No pudimos procesar el pago. Intentá de nuevo.');
            setLoading(false);
        }
    }

    return (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
            <div className="relative z-10 w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl space-y-4">
                <button
                    className="absolute top-3 right-3 rounded-full p-1.5 text-slate-400 hover:bg-slate-100"
                    onClick={onClose}
                    aria-label="Cerrar"
                >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>

                <p className="text-base font-bold text-slate-800">Elegí el monto de tu propina</p>

                <div className="grid grid-cols-2 gap-2">
                    {TIP_PRESETS.map((p) => (
                        <button
                            key={p}
                            type="button"
                            onClick={() => { setSelected(p); setCustom(''); }}
                            className={`rounded-xl border py-3 text-sm font-semibold transition-all ${selected === p
                                    ? 'border-transparent text-white'
                                    : 'border-slate-200 text-slate-700 hover:border-slate-300'
                                }`}
                            style={selected === p ? { backgroundColor: accentColor } : {}}
                        >
                            ${p.toLocaleString('es-AR')}
                        </button>
                    ))}
                </div>

                <div>
                    <label className="text-xs font-medium text-slate-600 mb-1 block">Otro monto</label>
                    <div className="flex items-center gap-1 rounded-xl border border-slate-200 px-3 py-2">
                        <span className="text-slate-400 text-sm">$</span>
                        <input
                            type="number"
                            min="10"
                            placeholder="Ingresar monto"
                            className="flex-1 bg-transparent text-sm outline-none"
                            value={custom}
                            onChange={(e) => { setCustom(e.target.value); setSelected(null); }}
                        />
                    </div>
                </div>

                {err && <p className="text-xs text-red-500">{err}</p>}

                <button
                    type="button"
                    disabled={!amount || loading}
                    onClick={handleConfirm}
                    className="w-full rounded-xl py-3 text-sm font-bold text-white transition-opacity hover:opacity-90 active:opacity-80 disabled:opacity-40"
                    style={{ backgroundColor: '#009ee3' }}
                >
                    {loading ? 'Redirigiendo...' : amount ? `Propina de $${amount.toLocaleString('es-AR')}` : 'Seleccioná un monto'}
                </button>
            </div>
        </div>
    );
}

// ─── Sticky CTA Bar ───────────────────────────────────────────────────────────
function StickyCTABar({
    engagement,
    accentColor,
    onTipClick,
    onReviewClick,
}: {
    engagement: PublicMenuEngagement;
    accentColor: string;
    onTipClick: () => void;
    onReviewClick: () => void;
}) {
    const hasTips = engagement.tips_enabled && (
        (engagement.tips_mode === 'mp_link' && !!engagement.mp_tip_url) ||
        (engagement.tips_mode === 'mp_qr_image' && !!engagement.mp_qr_image_url) ||
        engagement.tips_mode === 'mp_oauth_checkout'
    );
    const hasReviews = engagement.reviews_enabled && !!engagement.google_write_review_url;

    if (!hasTips && !hasReviews) return null;

    return (
        <div
            className="fixed bottom-0 left-0 right-0 z-40 flex gap-2 px-4 pb-[env(safe-area-inset-bottom,1rem)] pt-3 sm:bottom-6 sm:left-1/2 sm:right-auto sm:-translate-x-1/2 sm:flex-row sm:rounded-2xl sm:px-4 sm:shadow-2xl sm:border sm:border-white/10 sm:pb-3"
            style={{ background: 'rgba(10,10,10,0.88)', backdropFilter: 'blur(12px)' }}
        >
            {hasTips && (
                <button
                    type="button"
                    onClick={onTipClick}
                    className="flex flex-1 sm:flex-none items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold text-white transition-all active:scale-95"
                    style={{ backgroundColor: accentColor }}
                    aria-label="Dejar propina"
                >
                    <span aria-hidden>💸</span>
                    Propina
                </button>
            )}
            {hasReviews && (
                <button
                    type="button"
                    onClick={onReviewClick}
                    className="flex flex-1 sm:flex-none items-center justify-center gap-2 rounded-xl border border-white/20 px-5 py-2.5 text-sm font-semibold text-white transition-all hover:bg-white/10 active:scale-95"
                    aria-label="Dejar reseña en Google"
                >
                    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z" />
                    </svg>
                    Reseña
                </button>
            )}
        </div>
    );
}

// ─── Block Navigation (mobile chips) ─────────────────────────────────────────
function BlockNavChips({ blocks, accentColor }: { blocks: PublicMenuLayoutBlock[]; accentColor: string }) {
    if (blocks.length <= 1) return null;
    return (
        <nav
            aria-label="Secciones de la carta"
            className="sticky top-0 z-30 flex gap-2 overflow-x-auto py-2 -mx-6 px-6 lg:-mx-12 lg:px-12 2xl:-mx-16 2xl:px-16 bg-[var(--menu-bg)] border-b border-[var(--menu-divider)] mb-8"
            style={{ scrollbarWidth: 'none' }}
        >
            {blocks.map((block) => (
                <a
                    key={block.id}
                    href={`#block-${block.id}`}
                    className="whitespace-nowrap flex-shrink-0 rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-colors hover:opacity-80"
                    style={{ borderColor: accentColor, color: accentColor }}
                >
                    {block.badge_text ? `${block.title} · ${block.badge_text}` : block.title}
                </a>
            ))}
        </nav>
    );
}

// ─── Block Section Renderer ───────────────────────────────────────────────────
function menuBlockColumnsClass(colsDesktop: number, colsTablet: number, layout: string): string {
    const desktopMap: Record<number, string> = { 1: 'lg:columns-1', 2: 'lg:columns-2', 3: 'lg:columns-3', 4: 'lg:columns-4' };
    const tabletMap: Record<number, string> = { 1: 'md:columns-1', 2: 'md:columns-2', 3: 'md:columns-3' };
    const d = desktopMap[colsDesktop] || 'lg:columns-2';
    const t = tabletMap[colsTablet] || 'md:columns-2';
    return `columns-1 gap-12 [column-fill:balance] text-sm ${t} ${d}`;
}

function BlockSection({ block }: { block: PublicMenuLayoutBlock }) {
    // Filter: only categories that have items (backend already does is_active, but double-check)
    const visibleCategories = block.categories.filter((c) => c.items && c.items.length > 0);
    if (visibleCategories.length === 0) return null;

    return (
        <section id={`block-${block.id}`} className="mb-16 scroll-mt-20">
            {/* Block Header */}
            <div className="mb-8 flex items-center gap-4">
                <div className="flex flex-col gap-1">
                    <h2
                        className="font-bold uppercase tracking-widest text-[var(--menu-text)] font-[family-name:var(--menu-font-heading)] opacity-40"
                        style={{ fontSize: 'calc(var(--menu-size-body) * 0.75)' }}
                    >
                        {block.title}
                    </h2>
                    {block.badge_text && (
                        <span
                            className="inline-block rounded-full border px-2.5 py-0.5 text-[11px] font-semibold"
                            style={{ borderColor: 'var(--menu-accent)', color: 'var(--menu-accent)' }}
                        >
                            {block.badge_text}
                        </span>
                    )}
                </div>
                <div className="h-px flex-1 bg-[var(--menu-divider)] opacity-30" />
            </div>

            {/* Categories in columns */}
            <div className={menuBlockColumnsClass(block.columns_desktop, block.columns_tablet, block.layout)}>
                {visibleCategories.map((cat) => (
                    <MenuCategorySection
                        key={cat.id}
                        category={cat as any}          /* shape is compatible */
                    />
                ))}
            </div>
        </section>
    );
}

// ─── Main Layout ──────────────────────────────────────────────────────────────
export function PublicMenuLayout({ config, categories, layoutBlocks, engagement, slug }: PublicMenuLayoutProps) {
    const theme = config.theme_json || {};
    const accentColor = (theme as any).accent || '#8b5cf6';

    const [qrModalOpen, setQrModalOpen] = useState(false);
    const [tipSelectorOpen, setTipSelectorOpen] = useState(false);

    const handleTipClick = useCallback(() => {
        if (!engagement?.tips_enabled) return;
        if (engagement.tips_mode === 'mp_link' && engagement.mp_tip_url) {
            const isDesktop = typeof window !== 'undefined' && window.innerWidth >= 768;
            window.open(engagement.mp_tip_url, isDesktop ? '_blank' : '_self', 'noopener,noreferrer');
        } else if (engagement.tips_mode === 'mp_qr_image' && engagement.mp_qr_image_url) {
            setQrModalOpen(true);
        } else if (engagement.tips_mode === 'mp_oauth_checkout') {
            setTipSelectorOpen(true);
        }
    }, [engagement]);

    // Open review URL. On mobile/in-app browsers use same-tab navigation — popup
    // windows are blocked silently and create phantom chrome-error:// tabs.
    const handleReviewClick = useCallback(() => {
        const url = engagement?.google_write_review_url;
        if (!url) return;
        const isMobile = typeof window !== 'undefined' && window.innerWidth < 768;
        if (isMobile) {
            window.location.href = url;
        } else {
            window.open(url, '_blank', 'noopener,noreferrer');
        }
    }, [engagement]);

    // Construct CSS variables
    const styles = {
        '--menu-bg': (theme as any).background || '#0a0a0a',
        '--menu-text': (theme as any).text || '#ffffff',
        '--menu-muted': (theme as any).mutedText || '#a3a3a3',
        '--menu-accent': accentColor,
        '--menu-divider': (theme as any).divider || '#262626',
        '--menu-font-body': getMenuFontFamily((theme as any).bodyFont || (theme as any).fontFamily),
        '--menu-font-heading': getMenuFontFamily((theme as any).headingFont || (theme as any).bodyFont || (theme as any).fontFamily),
        '--menu-size-heading': `${(theme as any).menuHeadingFontSize || 1.25}rem`,
        '--menu-size-body': `${(theme as any).menuBodyFontSize || 1}rem`,
    } as React.CSSProperties;

    // Ensure body background matches theme (avoid white flickering or overscroll issues)
    useEffect(() => {
        const bg = (theme as any).background || '#0a0a0a';
        const prevHtmlBg = document.documentElement.style.backgroundColor;
        const prevBodyBg = document.body.style.backgroundColor;
        const prevBodyBgImage = document.body.style.backgroundImage;
        const prevBodyHeight = document.body.style.height;

        document.documentElement.style.backgroundColor = bg;
        document.body.style.backgroundColor = bg;
        document.body.style.backgroundImage = 'none';
        document.body.style.height = 'auto';
        document.body.style.minHeight = '100vh';

        return () => {
            document.documentElement.style.backgroundColor = prevHtmlBg;
            document.body.style.backgroundColor = prevBodyBg;
            document.body.style.backgroundImage = prevBodyBgImage;
            document.body.style.height = prevBodyHeight;
            document.body.style.minHeight = '';
        };
    }, [(theme as any).background]);

    const hasCtaBar = !!engagement && (
        (engagement.tips_enabled && (engagement.mp_tip_url || engagement.mp_qr_image_url || engagement.tips_mode === 'mp_oauth_checkout')) ||
        (engagement.reviews_enabled && !!engagement.google_write_review_url)
    );

    return (
        <>
            <main
                style={styles}
                className="relative flex-1 w-full bg-[var(--menu-bg)] text-[var(--menu-text)] font-[family-name:var(--menu-font-body)] selection:bg-[var(--menu-accent)] selection:text-[var(--menu-bg)] overflow-hidden"
            >
                {/* Watermark Background */}
                {(theme as any).menuLogoUrl && (theme as any).menuLogoPosition === 'watermark' && (
                    <div
                        aria-hidden="true"
                        className="pointer-events-none absolute inset-0 z-0 flex items-center justify-center p-12"
                        style={{ opacity: (theme as any).menuLogoWatermarkOpacity || 0.08 }}
                    >
                        <img
                            src={buildMediaUrl((theme as any).menuLogoUrl) ?? undefined}
                            alt=""
                            className="w-full max-w-3xl object-contain opacity-100 grayscale transition-all duration-300"
                            style={{ filter: 'grayscale(100%)' }}
                        />
                    </div>
                )}

                <div
                    className="relative z-10 w-full px-6 py-10 lg:px-12 2xl:px-16"
                    style={hasCtaBar ? { paddingBottom: '6rem' } : undefined}
                >
                    {/* Header */}
                    <MenuBrandHeader
                        brandDetails={{ name: config.brand_name, description: config.description }}
                        theme={theme as any}
                    />

                    {/* ── Block navigation chips (when layout blocks configured) ── */}
                    {layoutBlocks && layoutBlocks.length > 0 && (
                        <BlockNavChips blocks={layoutBlocks} accentColor={accentColor} />
                    )}

                    {/* ── Render by blocks OR fallback to flat categories ─────── */}
                    {layoutBlocks && layoutBlocks.length > 0 ? (
                        layoutBlocks.map((block) => (
                            <BlockSection key={block.id} block={block} />
                        ))
                    ) : (
                        /* Fallback: no layout configured → original flat columns */
                        <div className="columns-1 gap-12 text-sm [column-fill:balance] lg:columns-2 2xl:columns-3">
                            {categories.map((category) => (
                                <MenuCategorySection key={category.id} category={category} />
                            ))}
                        </div>
                    )}

                    {/* Footer */}
                    <div className="mt-20 border-t border-[var(--menu-divider)] pt-8 text-center text-xs text-[var(--menu-muted)] opacity-60">
                        <p>Precios e impuestos sujetos a cambios sin previo aviso.</p>
                        <p className="mt-1">© {new Date().getFullYear()} {config.brand_name} — Powered by Mirubro</p>
                    </div>
                </div>
            </main>

            {/* ── Sticky CTA Bar ────────────────────────────────────────────── */}
            {engagement && (
                <StickyCTABar
                    engagement={engagement}
                    accentColor={accentColor}
                    onTipClick={handleTipClick}
                    onReviewClick={handleReviewClick}
                />
            )}

            {/* ── QR Modal (tips_mode=mp_qr_image) ─────────────────────────── */}
            {engagement?.tips_enabled && engagement.tips_mode === 'mp_qr_image' && engagement.mp_qr_image_url && (
                <QRModal
                    open={qrModalOpen}
                    onClose={() => setQrModalOpen(false)}
                    qrImageUrl={engagement.mp_qr_image_url}
                    mpTipUrl={engagement.mp_tip_url}
                    accentColor={accentColor}
                />
            )}

            {/* ── Tip Amount Selector (tips_mode=mp_oauth_checkout) ──────────── */}
            {engagement?.tips_enabled && engagement.tips_mode === 'mp_oauth_checkout' && slug && (
                <TipAmountSelector
                    slug={slug}
                    accentColor={accentColor}
                    open={tipSelectorOpen}
                    onClose={() => setTipSelectorOpen(false)}
                />
            )}
        </>
    );
}
