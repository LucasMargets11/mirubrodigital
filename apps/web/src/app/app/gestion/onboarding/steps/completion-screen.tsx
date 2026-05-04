'use client';

import Link from 'next/link';

import { Button } from '@/components/ui/button';

export function CompletionScreen({ hasProducts }: { hasProducts: boolean }) {
    return (
        <div className="mx-auto max-w-xl space-y-8 py-12 text-center">
            {/* Icon */}
            <div className="flex justify-center">
                <div className="flex h-20 w-20 items-center justify-center rounded-full bg-emerald-100">
                    <svg className="h-10 w-10 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                </div>
            </div>

            {/* Text */}
            <div className="space-y-2">
                <h1 className="text-2xl font-bold text-slate-900">¡Tu negocio está listo!</h1>
                <p className="text-sm text-slate-500">
                    Ya podés empezar a vender, gestionar tu inventario y controlar tus finanzas desde un solo lugar.
                </p>
            </div>

            {/* CTAs */}
            <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
                {hasProducts ? (
                    <>
                        <Button asChild>
                            <Link href="/app/gestion/ventas/nueva">Registrar una venta</Link>
                        </Button>

                        <Button asChild variant="outline">
                            <Link href="/app/gestion/productos">Ver mis productos</Link>
                        </Button>

                        <Button asChild variant="ghost">
                            <Link href="/app/gestion/dashboard">Ir al panel de inicio</Link>
                        </Button>
                    </>
                ) : (
                    <>
                        <Button asChild>
                            <Link href="/app/gestion/productos">Cargar un producto</Link>
                        </Button>

                        <Button asChild variant="ghost">
                            <Link href="/app/gestion/dashboard">Ir al panel de inicio</Link>
                        </Button>
                    </>
                )}
            </div>
        </div>
    );
}
