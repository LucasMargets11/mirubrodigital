import { cn } from "@/lib/utils";
import { buildMediaUrl } from "@/lib/api-url";
import { MenuItem } from "./types";

interface MenuItemRowProps {
    item: MenuItem;
    currency?: string;
}

export function MenuItemRow({ item, currency = "$" }: MenuItemRowProps) {
    // Format price: remove .00 decimals if present
    const formattedPrice = String(item.price).replace(/\.00$/, '');
    const imgSrc = buildMediaUrl(item.image_url ?? item.image) ?? undefined;
    const hasImage = !!(item.image_url || item.image);

    return (
        <div className={cn("py-2", !item.is_available && "opacity-50 grayscale")}>
            {/* ── Desktop: original single-row layout ────────────────────── */}
            <div className="hidden lg:flex items-center justify-between gap-6">
                <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-center gap-2">
                        <h3
                            className="truncate font-medium text-[var(--menu-text)] font-[family-name:var(--menu-font-heading)]"
                            style={{ fontSize: 'var(--menu-size-body)', lineHeight: 1.25 }}
                        >
                            {item.name}
                        </h3>
                        {item.is_featured && (
                            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--menu-accent),transparent_90%)] text-xs text-[var(--menu-accent)]">
                                ★
                            </span>
                        )}
                        {!item.is_available && (
                            <span className="rounded bg-[var(--menu-divider)] px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-[var(--menu-muted)]">
                                Agotado
                            </span>
                        )}
                    </div>
                    {item.description && (
                        <p
                            className="leading-snug text-[var(--menu-muted)]"
                            style={{ fontSize: 'calc(var(--menu-size-body) * 0.85)' }}
                        >
                            {item.description}
                        </p>
                    )}
                </div>
                <div className="flex shrink-0 items-center gap-3">
                    {hasImage ? (
                        <div className="h-16 w-16 overflow-hidden rounded-xl bg-[var(--menu-divider)]">
                            <img src={imgSrc} alt={item.name} className="h-full w-full object-cover" loading="lazy" />
                        </div>
                    ) : null}
                    <div
                        className="whitespace-nowrap leading-none font-bold tabular-nums text-[var(--menu-accent)] font-[family-name:var(--menu-font-heading)]"
                        style={{ fontSize: 'var(--menu-size-body)' }}
                    >
                        {currency}{formattedPrice}
                    </div>
                </div>
            </div>

            {/* ── Mobile: gastronomic card layout ────────────────────────── */}
            <div className="flex lg:hidden gap-3">
                {/* Text column */}
                <div className="min-w-0 flex-1 flex flex-col justify-center gap-1">
                    <div className="flex items-center gap-1.5">
                        <h3
                            className="font-semibold text-[var(--menu-text)] font-[family-name:var(--menu-font-heading)] line-clamp-2"
                            style={{ fontSize: 'var(--menu-size-body)', lineHeight: 1.3 }}
                        >
                            {item.name}
                        </h3>
                        {item.is_featured && (
                            <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--menu-accent),transparent_90%)] text-[10px] text-[var(--menu-accent)]">
                                ★
                            </span>
                        )}
                    </div>
                    {item.description && (
                        <p
                            className="line-clamp-2 leading-snug text-[var(--menu-muted)]"
                            style={{ fontSize: 'calc(var(--menu-size-body) * 0.8)' }}
                        >
                            {item.description}
                        </p>
                    )}
                    <div className="flex items-center gap-2 mt-0.5">
                        <span
                            className="font-bold tabular-nums text-[var(--menu-accent)] font-[family-name:var(--menu-font-heading)]"
                            style={{ fontSize: 'var(--menu-size-body)' }}
                        >
                            {currency}{formattedPrice}
                        </span>
                        {!item.is_available && (
                            <span className="rounded bg-[var(--menu-divider)] px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-[var(--menu-muted)]">
                                Agotado
                            </span>
                        )}
                    </div>
                </div>
                {/* Image column */}
                {hasImage ? (
                    <div className="h-24 w-24 shrink-0 overflow-hidden rounded-xl bg-[var(--menu-divider)]">
                        <img src={imgSrc} alt={item.name} className="h-full w-full object-cover" loading="lazy" />
                    </div>
                ) : null}
            </div>
        </div>
    );
}
