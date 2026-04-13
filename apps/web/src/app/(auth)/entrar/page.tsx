import { Suspense } from 'react';
import type { Metadata } from 'next';
import { AuthForm } from '@/components/auth/auth-form';

export const metadata: Metadata = {
    title: 'Ingresar — Mirubro',
    description:
        'Gestioná tu negocio desde un solo lugar. Ingresá con Google o con tu email.',
    robots: { index: false, follow: true },
};

/**
 * Login/Signup page
 * 
 * Layout structure:
 * - This page is under (auth) route group with NO footer
 * - Section takes full height of main (flex-1 from parent layout)
 * - Content is vertically centered
 * - Footer is NOT rendered (controlled by auth layout)
 */
export default function EntrarPage() {
    return (
        <section className="flex-1 flex items-center justify-center">
            <div className="w-full">
                <div className="mx-auto max-w-7xl px-6 lg:px-10">
                    <div className="grid gap-10 lg:grid-cols-2 lg:gap-16 items-center">
                        <div className="max-w-xl space-y-4">
                            <p className="text-sm font-semibold uppercase tracking-wider text-brand-500">Plataforma de gestión</p>
                            <h1 className="text-4xl font-display font-bold tracking-tight text-slate-900 lg:text-5xl">Ingresá a MiRubro</h1>
                            <p className="text-lg leading-relaxed text-slate-600">
                                Gestioná tu negocio desde un solo lugar. Ingresá con Google o con tu email.
                            </p>
                        </div>
                        <div className="w-full">
                            <div className="w-full max-w-[520px] mx-auto lg:ml-auto lg:mr-0">
                                <div className="rounded-2xl border border-slate-200/60 bg-white px-8 py-8 sm:px-10 sm:py-9 shadow-xl shadow-slate-900/[0.04]">
                                    <Suspense>
                                        <AuthForm />
                                    </Suspense>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
