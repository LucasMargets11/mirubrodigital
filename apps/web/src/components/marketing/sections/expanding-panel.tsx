'use client';

import { useRef, useEffect, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { Layers, Settings, TrendingUp, type LucideIcon, ArrowRight, CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Feature Data Structure
 */
interface Feature {
  title: string;
  description: string;
  icon: LucideIcon;
  stepLabel: string;
}

const STEPS: Feature[] = [
  {
    title: "Elegí la propuesta que mejor encaja con tu negocio",
    description: "Analizá qué servicio y qué plan responden mejor a tu forma de trabajar, al volumen de tu operación y a los objetivos que querés alcanzar.",
    icon: Layers,
    stepLabel: "Paso 1"
  },
  {
    title: "Prepará una gestión más clara desde el inicio",
    description: "Configurá tu sistema con una estructura pensada para ordenar tareas, información y procesos clave sin sumar complejidad innecesaria.",
    icon: Settings,
    stepLabel: "Paso 2"
  },
  {
    title: "Convertí el orden en una ventaja para crecer",
    description: "Cuando tu negocio funciona con más claridad, cada decisión se vuelve más simple: organizás mejor, detectás oportunidades y trabajás con mayor previsión.",
    icon: TrendingUp,
    stepLabel: "Paso 3"
  }
];

// ── Lightweight scroll-progress hook ─────────────────────────────────────────
// Replaces framer-motion useScroll + useTransform with ~20 lines of vanilla JS.
// Matches offset: ["start end", "center center"].

function useScrollExpand(ref: React.RefObject<HTMLElement | null>) {
    const [progress, setProgress] = useState(0);

    useEffect(() => {
        const el = ref.current;
        if (!el) return;

        let ticking = false;
        const update = () => {
            const rect = el.getBoundingClientRect();
            const vh = window.innerHeight;
            // progress 0 → element top at viewport bottom
            // progress 1 → element center at viewport center
            const startPos = vh;
            const endPos = vh / 2 - rect.height / 2;
            const range = startPos - endPos;
            const raw = range > 0 ? (startPos - rect.top) / range : 0;
            setProgress(Math.max(0, Math.min(1, raw)));
            ticking = false;
        };

        const onScroll = () => {
            if (!ticking) {
                ticking = true;
                requestAnimationFrame(update);
            }
        };

        window.addEventListener('scroll', onScroll, { passive: true });
        update();
        return () => window.removeEventListener('scroll', onScroll);
    }, [ref]);

    return progress;
}

// ── Fade-in wrapper (IntersectionObserver, replaces motion whileInView) ──────

function FadeIn({
    children,
    className,
    delay = 0,
    rootMargin = '0px',
    threshold = 0.1,
}: {
    children: ReactNode;
    className?: string;
    delay?: number;
    rootMargin?: string;
    threshold?: number;
}) {
    const ref = useRef<HTMLDivElement>(null);
    const [visible, setVisible] = useState(false);

    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        const observer = new IntersectionObserver(
            ([entry]) => {
                if (entry?.isIntersecting) {
                    setVisible(true);
                    observer.disconnect();
                }
            },
            { threshold, rootMargin }
        );
        observer.observe(el);
        return () => observer.disconnect();
    }, [threshold, rootMargin]);

    return (
        <div
            ref={ref}
            className={className}
            style={{
                opacity: visible ? 1 : 0,
                transform: visible ? 'translateY(0)' : 'translateY(2.5rem)',
                transition: `opacity 0.7s ease-out ${delay}ms, transform 0.7s ease-out ${delay}ms`,
            }}
        >
            {children}
        </div>
    );
}

/**
 * ExpandingPanelSection
 *
 * Scroll-driven expanding panel — now powered by a lightweight scroll listener
 * and CSS transitions instead of framer-motion (~50 KB savings).
 */
export function ExpandingPanelSection() {
    const containerRef = useRef<HTMLElement>(null);
    const progress = useScrollExpand(containerRef);

    // Map scroll progress to visual transforms (matching original sub-ranges)
    const expandP = Math.min(1, progress / 0.5);   // [0→0.5] maps to [0→1]
    const opacityP = Math.min(1, progress / 0.2);   // [0→0.2] maps to [0→1]

    return (
        <section
            ref={containerRef}
            className="py-24 md:py-32 overflow-hidden bg-white flex flex-col items-center justify-center min-h-screen"
        >
            <div
                className="relative bg-black shadow-2xl overflow-hidden mx-auto will-change-transform flex flex-col"
                style={{
                    width: `${90 + expandP * 8}vw`,
                    opacity: 0.5 + opacityP * 0.5,
                    transform: `translateY(${100 - expandP * 100}px)`,
                    borderRadius: '2rem',
                }}
            >
                {/* Fondo con gradiente sutil para dar profundidad */}
                <div className="absolute inset-0 bg-gradient-to-br from-zinc-900 via-black to-zinc-900 opacity-50 z-0 pointer-events-none" />

                {/* Contenido Principal */}
                <div className="relative z-10 w-full max-w-7xl mx-auto px-6 py-16 md:px-12 md:py-24">

                    {/* Header del Panel */}
                    <FadeIn className="text-center mb-16 md:mb-24 max-w-3xl mx-auto" delay={200}>
                        <h2 className="text-3xl md:text-5xl font-bold text-white tracking-tight mb-6">
                            Una forma más simple de poner en orden tu negocio
                        </h2>
                        <div className="h-1 w-24 bg-brand-500 mx-auto rounded-full mb-8" />
                        <p className="text-lg md:text-xl text-zinc-400 leading-relaxed">
                            MiRubro te acompaña desde la elección inicial hasta la puesta en marcha del sistema, para que empieces a trabajar con más organización y menos fricción.
                        </p>
                    </FadeIn>

                    {/* Features Grid */}
                    <div className="space-y-24 md:space-y-32">
                        {STEPS.map((step, index) => (
                            <StepBlock
                                key={index}
                                feature={step}
                                index={index}
                            />
                        ))}
                    </div>

                    {/* Footer CTA */}
                    <FadeIn className="mt-24 text-center" delay={400}>
                        <Link
                            href="/pricing"
                            className="group inline-flex items-center gap-2 px-8 py-4 bg-white text-black rounded-full font-bold text-lg hover:bg-gray-100 transition-colors"
                        >
                            Empezar ahora
                            <ArrowRight className="w-5 h-5 transition-transform group-hover:translate-x-1" />
                        </Link>
                    </FadeIn>

                </div>
            </div>
        </section>
    );
}

function StepBlock({ feature, index }: { feature: Feature; index: number }) {
    const isEven = index % 2 === 0;
    const visualRef = useRef<HTMLDivElement>(null);
    const [active, setActive] = useState(false);

    // Viewport-aware activation (mirrors framer-motion margin: "-20% 0px -20% 0px")
    useEffect(() => {
        const el = visualRef.current;
        if (!el) return;
        const observer = new IntersectionObserver(
            ([entry]) => setActive(!!entry?.isIntersecting),
            { threshold: 0.4, rootMargin: '-20% 0px -20% 0px' }
        );
        observer.observe(el);
        return () => observer.disconnect();
    }, []);

    const Icon = feature.icon;

    return (
        <FadeIn
            className="grid grid-cols-1 md:grid-cols-2 gap-12 md:gap-24 items-center"
            delay={index * 100}
        >
            {/*
                TEXT COLUMN
                En Desktop: Si es par (0, 2), va a la izquierda (orden natural).
                Si es impar (1), va a la derecha (order-2).
                En Mobile: Siempre primero (orden natural).
            */}
            <div className={cn(
                "space-y-6 md:space-y-8",
                !isEven && "md:order-2"
            )}>
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-zinc-800/50 border border-zinc-700 text-sm md:text-base text-zinc-300 w-fit font-medium tracking-wide shadow-sm backdrop-blur-md">
                    <span className="w-2 h-2 rounded-full bg-brand-500 animate-pulse" />
                    {feature.stepLabel}
                </div>

                <h3 className="text-3xl md:text-4xl font-bold text-white leading-tight">
                    {feature.title}
                </h3>

                <p className="text-lg md:text-xl text-zinc-400 leading-relaxed max-w-lg">
                    {feature.description}
                </p>

                {/* Optional details list */}
                <ul className="space-y-3 pt-4 border-t border-zinc-800/50 mt-6">
                    <li className="flex items-start gap-3 text-zinc-500" style={{ opacity: active ? 1 : 0.7, transition: 'opacity 0.5s ease' }}>
                        <div className={cn("mt-1 transition-colors duration-500", active ? "text-[#6366f1]" : "text-zinc-600")}>
                            <CheckCircle2 className="w-5 h-5" />
                        </div>
                        <span className="text-sm md:text-base">Proceso guiado y soporte continuo.</span>
                    </li>
                </ul>
            </div>

            {/*
                VISUAL COLUMN
                Border, glow, and icon scale activated by IntersectionObserver.
            */}
            <div
                ref={visualRef}
                className={cn(
                    "relative aspect-square md:aspect-[4/3] w-full rounded-2xl md:rounded-3xl overflow-hidden bg-zinc-900 border flex items-center justify-center p-8 transition-all duration-500",
                    !isEven && "md:order-1",
                    active ? "border-zinc-700" : "border-zinc-800/50"
                )}
            >
                {/* Decorative background glow */}
                <div
                    className="absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-zinc-800/30 via-transparent to-transparent transition-opacity duration-700"
                    style={{ opacity: active ? 1 : 0 }}
                />

                {/* Icon Container */}
                <div
                    className={cn(
                        "relative z-10 p-8 rounded-full bg-black/40 backdrop-blur-sm border transition-all duration-500",
                        active
                            ? "border-[rgba(99,102,241,0.3)] text-[#6366f1] scale-110"
                            : "border-zinc-800 text-zinc-300 scale-100"
                    )}
                >
                    <Icon strokeWidth={1.5} className="w-24 h-24 md:w-32 md:h-32" />
                </div>

                {/* Corner accents */}
                <div className="absolute top-0 left-0 w-20 h-20 bg-gradient-to-br from-white/5 to-transparent rounded-tl-3xl opacity-50" />
                <div className="absolute bottom-0 right-0 w-20 h-20 bg-gradient-to-tl from-white/5 to-transparent rounded-br-3xl opacity-50" />
            </div>
        </FadeIn>
    );
}