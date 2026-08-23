import { Suspense } from 'react';
import type { Metadata } from 'next';
import Link from 'next/link';
import { AuthForm } from '@/components/auth/auth-form';

export const metadata: Metadata = {
    title: 'Ingresar como cliente — Mirubro',
    description: 'Ingresá con la cuenta de Google registrada para tu comercio.',
    robots: { index: false, follow: true },
};

export default function ClienteEntrarPage() {
    return (
        <section className="flex flex-1 items-center justify-center">
            <div className="w-full">
                <div className="mx-auto max-w-7xl px-6 lg:px-10">
                    <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
                        <div className="max-w-xl space-y-4">
                            <p className="text-sm font-semibold uppercase tracking-wider text-brand-500">
                                Acceso para clientes
                            </p>
                            <h1 className="font-display text-4xl font-bold tracking-tight text-slate-900 lg:text-5xl">
                                Ingresar a Mi Rubro
                            </h1>
                            <p className="text-lg leading-relaxed text-slate-600">
                                Usá la cuenta de Google registrada cuando se creó tu comercio
                            </p>
                        </div>
                        <div className="w-full">
                            <div className="mx-auto w-full max-w-[520px] lg:ml-auto lg:mr-0">
                                <div className="rounded-2xl border border-slate-200/60 bg-white px-8 py-8 shadow-xl shadow-slate-900/[0.04] sm:px-10 sm:py-9">
                                    <Suspense>
                                        <AuthForm googleEndpoint="preauthorized" googleOnly />
                                    </Suspense>
                                    <div className="mt-6 border-t border-slate-100 pt-5 text-center">
                                        <Link
                                            href="/entrar"
                                            className="text-sm text-slate-500 transition-colors hover:text-brand-600"
                                        >
                                            Volver al ingreso habitual
                                        </Link>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
