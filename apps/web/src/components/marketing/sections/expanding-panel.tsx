'use client';

import { useRef } from 'react';
import { motion, useScroll, useTransform } from 'framer-motion';
import Link from 'next/link';
import { Layers, Settings, TrendingUp, LucideIcon, ArrowRight, CheckCircle2 } from 'lucide-react';
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

/**
 * ExpandingPanelSection
 * 
 * Componente visual que presenta un panel negro expandible al hacer scroll.
 * Contiene una guía de 3 pasos para empezar con MiRubro.
 */
export function ExpandingPanelSection() {
    const containerRef = useRef<HTMLElement>(null);

    const { scrollYProgress } = useScroll({
        target: containerRef,
        offset: ["start end", "center center"], 
    });

    // Transformaciones de expansión
    // Se completan al 50% del scroll para que la sensación de expansión sea mucho más rápida (2x)
    const width = useTransform(scrollYProgress, [0, 0.5], ["90vw", "98vw"]);
    const opacity = useTransform(scrollYProgress, [0, 0.2], [0.5, 1]);
    const y = useTransform(scrollYProgress, [0, 0.5], [100, 0]);
    const borderRadius = useTransform(scrollYProgress, [0, 0.5], ["2rem", "2rem"]);

    return (
        <section 
            ref={containerRef} 
            className="py-24 md:py-32 overflow-hidden bg-white flex flex-col items-center justify-center min-h-screen"
        >
            <motion.div
                style={{ 
                    width, 
                    opacity,
                    y,
                    borderRadius
                }}
                className="relative bg-black shadow-2xl overflow-hidden mx-auto will-change-transform flex flex-col"
            >
                {/* Fondo con gradiente sutil para dar profundidad */}
                <div className="absolute inset-0 bg-gradient-to-br from-zinc-900 via-black to-zinc-900 opacity-50 z-0 pointer-events-none" />
                
                {/* Contenido Principal */}
                <div className="relative z-10 w-full max-w-7xl mx-auto px-6 py-16 md:px-12 md:py-24">
                    
                    {/* Header del Panel */}
                    <motion.div 
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.8, delay: 0.2 }}
                        viewport={{ once: true }}
                        className="text-center mb-16 md:mb-24 max-w-3xl mx-auto"
                    >
                        <h2 className="text-3xl md:text-5xl font-bold text-white tracking-tight mb-6">
                            Una forma más simple de poner en orden tu negocio
                        </h2>
                        <div className="h-1 w-24 bg-brand-500 mx-auto rounded-full mb-8" />
                        <p className="text-lg md:text-xl text-zinc-400 leading-relaxed">
                            MiRubro te acompaña desde la elección inicial hasta la puesta en marcha del sistema, para que empieces a trabajar con más organización y menos fricción.
                        </p>
                    </motion.div>

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
                    <motion.div 
                        initial={{ opacity: 0 }}
                        whileInView={{ opacity: 1 }}
                        transition={{ duration: 0.5, delay: 0.4 }}
                        viewport={{ once: true }}
                        className="mt-24 text-center"
                    >
                        <Link
                            href="/pricing"
                            className="group inline-flex items-center gap-2 px-8 py-4 bg-white text-black rounded-full font-bold text-lg hover:bg-gray-100 transition-colors"
                        >
                            Empezar ahora
                            <ArrowRight className="w-5 h-5 transition-transform group-hover:translate-x-1" />
                        </Link>
                    </motion.div>

                </div>
            </motion.div>
        </section>
    );
}

function StepBlock({ feature, index }: { feature: Feature; index: number }) {
    const isEven = index % 2 === 0;

    return (
        <motion.div 
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: "easeOut", delay: index * 0.1 }}
            viewport={{ once: true, margin: "-100px" }}
            className="grid grid-cols-1 md:grid-cols-2 gap-12 md:gap-24 items-center"
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

                {/* Optional details list if needed, kept for structure but simplified */}
                <ul className="space-y-3 pt-4 border-t border-zinc-800/50 mt-6">
                    <motion.li 
                        className="flex items-start gap-3 text-zinc-500"
                        initial="idle"
                        whileInView="active"
                        viewport={{ margin: "-20% 0px -20% 0px" }}
                        variants={{
                            idle: { opacity: 0.7 },
                            active: { opacity: 1 }
                        }}
                    >
                       <motion.div
                            variants={{
                                idle: { color: "rgb(82 82 91)" }, // zinc-600
                                active: { color: "#6366f1" } // brand-500
                            }}
                            className="mt-1"
                       >
                            <CheckCircle2 className="w-5 h-5 transition-colors" />
                       </motion.div>
                       <span className="text-sm md:text-base">Proceso guiado y soporte continuo.</span>
                    </motion.li>
                </ul>
            </div>

            {/* 
                VISUAL COLUMN
                Reemplazamos efectos hover por variants "active" que se disparan
                cuando el elemento entra en la zona principal del viewport.
            */}
            <motion.div 
                className={cn(
                    "relative aspect-square md:aspect-[4/3] w-full rounded-2xl md:rounded-3xl overflow-hidden bg-zinc-900 border flex items-center justify-center p-8 transition-colors",
                    !isEven && "md:order-1"
                )}
                initial="idle"
                whileInView="active"
                viewport={{ margin: "-20% 0px -20% 0px", amount: 0.4 }}
                variants={{
                    idle: { borderColor: "rgba(39, 39, 42, 0.5)" }, // zinc-800/50
                    active: { borderColor: "rgba(63, 63, 70, 1)" }  // zinc-700
                }}
                transition={{ duration: 0.5 }}
            >
                {/* Decorative background elements - Se ilumina al hacer foco */}
                <motion.div 
                    className="absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-zinc-800/30 via-transparent to-transparent" 
                    variants={{
                        idle: { opacity: 0 },
                        active: { opacity: 1 }
                    }}
                    transition={{ duration: 0.7 }}
                />
                
                {/* Icon Container - Escala y Color al hacer foco */}
                <motion.div 
                    className="relative z-10 p-8 rounded-full bg-black/40 backdrop-blur-sm border transition-all"
                    variants={{
                        idle: { 
                            borderColor: "rgb(39 39 42)", // zinc-800
                            color: "rgb(212 212 216)", // zinc-300
                            scale: 1
                        },
                        active: { 
                            borderColor: "rgba(99, 102, 241, 0.3)", // brand-500/30
                            color: "#6366f1", // brand-500
                            scale: 1.1
                        }
                    }}
                    transition={{ duration: 0.5 }}
                >
                    <feature.icon strokeWidth={1.5} className="w-24 h-24 md:w-32 md:h-32" />
                </motion.div>

                {/* Corner accents */}
                <div className="absolute top-0 left-0 w-20 h-20 bg-gradient-to-br from-white/5 to-transparent rounded-tl-3xl opacity-50" />
                <div className="absolute bottom-0 right-0 w-20 h-20 bg-gradient-to-tl from-white/5 to-transparent rounded-br-3xl opacity-50" />
            </motion.div>
        </motion.div>
    );
}