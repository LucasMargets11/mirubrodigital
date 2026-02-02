import { MenuCategory } from "./types";
import { MenuItemRow } from "./item-row";

interface MenuCategorySectionProps {
    category: MenuCategory;
    id?: string;
}

export function MenuCategorySection({ category, id }: MenuCategorySectionProps) {
    if (!category.items.length) return null;

    return (
        <section id={id} className="mb-12 break-inside-avoid">
            <div className="mb-6 flex items-center gap-4">
                <h2 
                    className="font-bold uppercase tracking-wide text-[var(--menu-accent)] font-[family-name:var(--menu-font-heading)]"
                    style={{ fontSize: 'var(--menu-size-heading)', lineHeight: 1.2 }}
                >
                    {category.name}
                </h2>
                <div className="h-px flex-1 bg-[var(--menu-divider)]" />
            </div>
            {category.description && (
                <p 
                    className="mb-6 italic text-[var(--menu-muted)]"
                    style={{ fontSize: 'calc(var(--menu-size-body) * 0.85)', lineHeight: 1.4 }}
                >
                    {category.description}
                </p>
            )}
            <div className="space-y-4">
                {category.items.map((item) => (
                    <MenuItemRow key={item.id} item={item} />
                ))}
            </div>
        </section>
    );
}
