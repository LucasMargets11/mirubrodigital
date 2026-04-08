import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { HERO_PROOF_POINTS } from './data';
import { ArrowRight, CheckCircle2 } from 'lucide-react';

export function HeroSection() {
    return (
        <section className="relative w-full overflow-hidden bg-white pt-24 pb-16 lg:pt-0 lg:pb-0 min-h-[calc(100vh-3.5rem)] lg:min-h-[calc(100vh-4rem)] flex items-center">
            {/* Background Decor */}
            <div className="absolute inset-0 -z-10 pointer-events-none overflow-hidden">
                <div className="absolute top-[-10%] right-[-5%] w-[40%] h-[40%] bg-brand-50/60 rounded-full blur-3xl opacity-50" />
                <div className="absolute bottom-[-10%] left-[-10%] w-[40%] h-[40%] bg-indigo-50/60 rounded-full blur-3xl opacity-50" />
            </div>

            <div className="mx-auto max-w-7xl px-6 lg:px-10 w-full h-full">
                <div className="grid gap-12 lg:grid-cols-2 lg:gap-16 items-center h-full">
                    {/* Left Column: Content */}
                    <div className="max-w-xl space-y-8 flex flex-col justify-center py-8 lg:py-0">
                        
                        {/* Heading */}
                        <div className="space-y-6">
                            <h1 className="font-display font-bold text-slate-900 tracking-tight leading-[1.05]">
                                <span style={{ fontSize: 'clamp(2.5rem, 4.5vw, 4.25rem)' }}>
                                    Centraliza tus{' '}
                                    <br className="hidden lg:block" />
                                    operaciones{' '}
                                    <br className="hidden lg:block" />
                                    en una sola
                                </span>
                                <br />
                                <span className="text-brand-600 relative inline-block tracking-tight" style={{ fontSize: 'clamp(3.25rem, 6vw, 5.5rem)' }}>
                                    plataforma
                                    <svg className="absolute w-full h-3 -bottom-1 left-0 text-brand-200 -z-10" viewBox="0 0 100 10" preserveAspectRatio="none">
                                        <path d="M0 5 Q 50 10 100 5" stroke="currentColor" strokeWidth="8" fill="none" opacity="0.6" />
                                    </svg>
                                </span>
                            </h1>
                            <p className="text-lg text-slate-600 leading-relaxed max-w-lg font-normal"
                               style={{ fontSize: 'clamp(1rem, 1.15vw, 1.125rem)' }}>
                                Todo lo que necesitás para vender mejor, ordenar tu negocio y potenciar tu crecimiento: gestión comercial, carta online, reseñas QR y reportes en tiempo real.
                            </p>
                        </div>

                        {/* CTAs */}
                        <div className="flex flex-col sm:flex-row gap-4 pt-2">
                            <Button asChild size="lg" className="h-12 px-8 text-base text-white shadow-lg shadow-brand-500/25 hover:shadow-brand-500/40 transition-all font-semibold bg-brand-600 hover:bg-brand-500">
                                <Link href="/entrar">
                                    Comenzar ahora
                                    <ArrowRight className="ml-2 h-4 w-4" />
                                </Link>
                            </Button>
                            <Button asChild variant="outline" size="lg" className="h-12 px-8 text-base border-slate-200 hover:bg-slate-50 text-slate-700 hover:text-slate-900 bg-transparent">
                                <Link href="/pricing">
                                    Ver Precios
                                </Link>
                            </Button>
                        </div>

                        {/* Proof Points */}
                        <div className="pt-6 border-t border-slate-100">
                            <div className="flex flex-wrap gap-x-6 gap-y-3 text-sm font-medium text-slate-500">
                                {HERO_PROOF_POINTS.map((point) => (
                                    <span key={point} className="flex items-center gap-2 transition-colors hover:text-brand-600">
                                        <CheckCircle2 className="h-4.5 w-4.5 text-brand-500 flex-shrink-0" />
                                        {point}
                                    </span>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Right Column: Mockups Composition */}
                    <div className="relative w-full aspect-square lg:aspect-[4/3] flex items-center justify-center lg:justify-end select-none pointer-events-none lg:pointer-events-auto mt-8 lg:mt-0">
                        {/* 
                            MOCKUPS SYSTEM:
                            Using strict aspect ratios and relative positioning to maintain layout integrity.
                            Replace background colors/divs with Image components when assets are available.
                        */}
                        
                        {/* 1. Desktop Mockup (Main) */}
                        <div className="absolute top-[10%] lg:top-[15%] right-0 w-[90%] lg:w-[85%] aspect-[16/10] rounded-xl shadow-[0_20px_50px_-12px_rgba(0,0,0,0.12)] bg-white border border-slate-200 overflow-hidden z-10 transform hover:scale-[1.01] transition-transform duration-500">
                            {/* Browser UI Bar */}
                            <div className="h-7 bg-slate-50 border-b border-slate-100 flex items-center gap-1.5 px-3">
                                <div className="flex gap-1.5">
                                    <div className="w-2.5 h-2.5 rounded-full bg-red-400/20 border border-red-500/30"></div>
                                    <div className="w-2.5 h-2.5 rounded-full bg-amber-400/20 border border-amber-500/30"></div>
                                    <div className="w-2.5 h-2.5 rounded-full bg-emerald-400/20 border border-emerald-500/30"></div>
                                </div>
                                <div className="ml-4 flex-1 h-4 bg-white rounded-md border border-slate-100/50 shadow-sm max-w-[200px]"></div>
                            </div>
                            {/* Content Area - Placeholder for Dashboard Screenshot */}
                            <div className="relative w-full h-full bg-slate-50 flex flex-col p-4">
                                {/* Header Placeholder */}
                                <div className="w-full h-12 bg-white rounded-lg border border-slate-100 shadow-sm mb-4"></div>
                                <div className="flex gap-4 h-full pb-8">
                                    {/* Sidebar */}
                                    <div className="w-16 lg:w-48 hidden sm:block h-full bg-white rounded-lg border border-slate-100 shadow-sm"></div>
                                    {/* Main Content */}
                                    <div className="flex-1 h-full bg-white rounded-lg border border-slate-100 shadow-sm p-4 grid grid-cols-2 gap-4">
                                        <div className="col-span-2 h-24 bg-brand-50/30 rounded border border-brand-100/20"></div>
                                        <div className="h-32 bg-slate-50 rounded"></div>
                                        <div className="h-32 bg-slate-50 rounded"></div>
                                    </div>
                                </div>
                                {/* Overlay Label (Remove when real image is used) */}
                                <div className="absolute inset-0 flex items-center justify-center bg-white/40 backdrop-blur-[1px]">
                                    <p className="text-slate-400 text-sm font-medium uppercase tracking-widest border border-slate-200 px-4 py-2 rounded bg-white shadow-sm">
                                        Dashboard Principal
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* 2. Tablet/POS Mockup (Bottom Left) */}
                        <div className="absolute bottom-[10%] left-0 lg:-left-2 w-[45%] lg:w-[48%] aspect-[4/3] rounded-lg shadow-[0_20px_40px_-12px_rgba(0,0,0,0.15)] bg-white border border-slate-200 z-20 overflow-hidden transform hover:-translate-y-1 transition-transform duration-300">
                             <div className="h-full w-full bg-slate-50 relative p-3">
                                <div className="h-full w-full bg-white rounded shadow-sm border border-slate-100 flex flex-col p-2">
                                     <div className="h-8 w-full bg-slate-100 rounded mb-2"></div>
                                     <div className="grid grid-cols-2 gap-2 flex-1">
                                        <div className="bg-brand-50/20 rounded border border-brand-100/20"></div>
                                        <div className="bg-brand-50/20 rounded border border-brand-100/20"></div>
                                        <div className="bg-brand-50/20 rounded border border-brand-100/20"></div>
                                        <div className="bg-brand-50/20 rounded border border-brand-100/20"></div>
                                     </div>
                                </div>
                                <div className="absolute bottom-4 left-0 right-0 text-center">
                                    <span className="text-[10px] sm:text-xs text-slate-500 font-semibold bg-white/90 px-2 py-0.5 rounded shadow-sm border border-slate-100">POS / Tablet</span>
                                </div>
                             </div>
                        </div>

                        {/* 3. Mobile Mockup (Bottom Right) */}
                        <div className="absolute bottom-[5%] right-[5%] lg:right-[15%] w-[20%] lg:w-[22%] aspect-[9/19] rounded-[2rem] shadow-[0_25px_50px_-12px_rgba(0,0,0,0.25)] bg-slate-900 border-[6px] border-slate-900 z-30 overflow-hidden">
                             {/* Screen */}
                             <div className="w-full h-full bg-white rounded-[1.5rem] overflow-hidden relative">
                                <div className="absolute top-0 inset-x-0 h-6 bg-slate-100 z-10 flex justify-center">
                                    <div className="w-16 h-4 bg-slate-900 rounded-b-lg"></div>
                                </div>
                                <div className="pt-8 px-2 pb-2 h-full flex flex-col gap-2">
                                    <div className="w-full h-12 bg-indigo-50 rounded-lg"></div>
                                    <div className="w-full h-20 bg-slate-50 rounded-lg"></div>
                                    <div className="w-full flex-1 bg-slate-50 rounded-lg"></div>
                                </div>
                                <div className="absolute bottom-4 left-0 right-0 text-center">
                                    <span className="text-[8px] text-slate-400 font-bold uppercase">Mobile App</span>
                                </div>
                             </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
