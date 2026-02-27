import { cn } from '@/lib/utils';

/**
 * SiteContainer — single source of truth for horizontal layout.
 *
 * Canonical values (must match across header, footer and all page sections):
 *   max-width : max-w-7xl  (1280px)
 *   padding-x : px-6  → lg:px-10
 *   centering : mx-auto
 *
 * Usage:
 *   <SiteContainer>…content…</SiteContainer>
 *   <SiteContainer className="py-16">…content with vertical padding…</SiteContainer>
 *
 * Rules:
 *   ✅ Every section that needs to align with the header uses this component.
 *   ❌ Never re-declare max-w-* or px-* for layout purposes outside this component.
 *   ❌ Never add padding-x to the outer wrapper — only this component controls it.
 */
export function SiteContainer({
    children,
    className,
    as: Tag = 'div',
}: {
    children: React.ReactNode;
    className?: string;
    as?: React.ElementType;
}) {
    return (
        <Tag className={cn('mx-auto w-full max-w-7xl px-6 lg:px-10', className)}>
            {children}
        </Tag>
    );
}
