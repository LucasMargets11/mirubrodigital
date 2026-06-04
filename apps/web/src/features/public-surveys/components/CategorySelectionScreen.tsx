'use client';

import { useEffect, useRef } from 'react';
import {
    ClipboardCheck,
    Headphones,
    Sparkles,
    Star,
    Timer,
    Utensils,
    type LucideIcon,
} from 'lucide-react';

import type { SurveyCategory, SurveyCategoryIconName } from '../types';

/** Mapa estático de íconos. Mantener sincronizado con `SurveyCategoryIconName`. */
const ICON_MAP: Record<SurveyCategoryIconName, LucideIcon> = {
    Headphones,
    Timer,
    Sparkles,
    Utensils,
    ClipboardCheck,
    Star,
};

interface Props {
    title?: string;
    subtitle?: string;
    categories: SurveyCategory[];
    onSelect: (category: SurveyCategory) => void;
}

export function CategorySelectionScreen({
    title = '¿Sobre qué querés opinar?',
    subtitle,
    categories,
    onSelect,
}: Props) {
    /**
     * Al montar la pantalla (entrar al step 'category' desde la intro o
     * volver desde una pregunta), reposicionamos el viewport sobre el
     * título y le movemos el foco. Esto evita que en mobile el header
     * domine la vista y obligue al usuario a scrollear para ver las cards.
     *
     * Usamos `requestAnimationFrame` para esperar al primer paint y
     * `scrollIntoView({ block: 'start' })` apuntando al título — así el
     * título queda arriba y debajo se ven las primeras filas de cards.
     */
    const titleRef = useRef<HTMLHeadingElement | null>(null);

    useEffect(() => {
        const raf = window.requestAnimationFrame(() => {
            const el = titleRef.current;
            if (!el) return;
            el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            // Mover foco al título mejora a11y (lectores + teclado) sin
            // generar scroll extra porque ya está en viewport.
            el.focus({ preventScroll: true });
        });
        return () => window.cancelAnimationFrame(raf);
    }, []);

    return (
        <div className="flex flex-col gap-5">
            <div className="space-y-1.5">
                <h2
                    ref={titleRef}
                    tabIndex={-1}
                    className="text-[22px] font-bold leading-tight text-black break-words focus:outline-none"
                >
                    {title}
                </h2>
                {subtitle && (
                    <p className="text-[13px] leading-snug text-slate-500 break-words">
                        {subtitle}
                    </p>
                )}
            </div>

            <div
                className="grid grid-cols-2 gap-3"
                role="list"
                aria-label="Categorías disponibles"
            >
                {categories.map((cat) => {
                    const Icon = cat.iconName ? ICON_MAP[cat.iconName] : null;
                    return (
                        <button
                            key={cat.id}
                            type="button"
                            role="listitem"
                            aria-label={`Seleccionar categoría ${cat.label}`}
                            onClick={() => onSelect(cat)}
                            className="group flex aspect-square w-full flex-col items-center justify-center gap-2.5 rounded-2xl border-2 border-[#FFC72C] bg-white p-3 text-center transition-colors active:scale-[0.97] hover:bg-[#FFF7E0] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#DA291C] focus-visible:ring-offset-2"
                        >
                            <span
                                aria-hidden="true"
                                className="flex h-14 w-14 items-center justify-center text-[#FFC72C]"
                            >
                                {Icon ? (
                                    <Icon className="h-12 w-12" strokeWidth={1.75} />
                                ) : (
                                    <span className="text-3xl font-black">·</span>
                                )}
                            </span>
                            <span className="text-[13px] font-bold leading-tight text-[#27251F] break-words">
                                {cat.label}
                            </span>
                        </button>
                    );
                })}
            </div>
        </div>
    );
}
