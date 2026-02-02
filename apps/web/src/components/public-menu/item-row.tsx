import { cn } from "@/lib/utils";
import { MenuItem } from "./types";

interface MenuItemRowProps {
    item: MenuItem;
    currency?: string;
}

export function MenuItemRow({ item, currency = "$" }: MenuItemRowProps) {
    // Format price: remove .00 decimals if present
    const formattedPrice = String(item.price).replace(/\.00$/, '');

    return (
        <div className={cn("flex items-start justify-between gap-6 py-2", !item.is_available && "opacity-50 grayscale")}>
            <div className="flex-1 space-y-1">
                <div className="flex items-center gap-2">
                    <h3 
                        className="font-medium text-[var(--menu-text)] font-[family-name:var(--menu-font-heading)]"
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
            <div 
                className="shrink-0 font-bold tabular-nums text-[var(--menu-accent)] font-[family-name:var(--menu-font-heading)]"
                style={{ fontSize: 'var(--menu-size-body)' }}
            >
                {currency}{formattedPrice}
            </div>
        </div>
    );
}
