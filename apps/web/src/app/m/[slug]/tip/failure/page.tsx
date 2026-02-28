"use client";

import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import type { Route } from "next";

export default function TipFailurePage() {
    const params = useParams<{ slug: string }>();
    const searchParams = useSearchParams();
    const slug = params.slug;
    // Mercado Pago may pass these on failure
    const tipId = searchParams.get("tip_id");
    const errorCode = searchParams.get("error_code");

    return (
        <main className="flex min-h-screen flex-col items-center justify-center bg-neutral-950 text-white px-4">
            <div className="w-full max-w-sm rounded-2xl bg-neutral-900 p-8 text-center space-y-6 shadow-2xl">
                {/* Icon */}
                <div className="flex items-center justify-center">
                    <span className="flex h-16 w-16 items-center justify-center rounded-full bg-red-500/20 text-4xl">
                        ✗
                    </span>
                </div>

                {/* Heading */}
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">
                        El pago no se completó
                    </h1>
                    <p className="mt-2 text-neutral-400 text-sm">
                        {errorCode
                            ? `Hubo un problema con el pago (código: ${errorCode}). Podés intentarlo de nuevo.`
                            : "Hubo un problema al procesar tu pago. Por favor, intentá de nuevo."}
                    </p>
                </div>

                {/* CTAs */}
                <div className="flex flex-col gap-3 pt-2">
                    {/* Retry — re-open tip selector on the menu page */}
                    <Link
                        href={`/m/${slug}?retry_tip=1${tipId ? `&tip_id=${tipId}` : ""}` as Route}
                        className="rounded-xl bg-violet-600 px-6 py-3 text-sm font-semibold text-white hover:bg-violet-500 transition-colors"
                    >
                        Intentar de nuevo
                    </Link>
                    <Link
                        href={`/m/${slug}`}
                        className="rounded-xl bg-neutral-800 px-6 py-3 text-sm font-medium text-white hover:bg-neutral-700 transition-colors ring-1 ring-white/10"
                    >
                        Volver a la carta
                    </Link>
                </div>

                {/* Support hint */}
                <p className="text-xs text-neutral-600 pt-2">
                    Si el problema persiste, verificá que tu medio de pago esté activo en Mercado Pago.
                </p>
            </div>

            {/* Powered by */}
            <p className="mt-8 text-xs text-neutral-600">
                Pagos procesados por Mercado Pago
            </p>
        </main>
    );
}
