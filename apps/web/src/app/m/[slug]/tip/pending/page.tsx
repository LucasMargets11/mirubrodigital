"use client";

import { useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { verifyPublicTip } from "@/features/menu/api";
import type { Route } from "next";

export default function TipPendingPage() {
    const params = useParams<{ slug: string }>();
    const searchParams = useSearchParams();
    const router = useRouter();
    const slug = params.slug;
    const tipId = searchParams.get("tip_id");
    const rawPaymentId =
        searchParams.get("payment_id") ?? searchParams.get("collection_id") ?? null;

    const [verifying, setVerifying] = useState(false);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);

    async function handleVerify() {
        if (!tipId || !rawPaymentId) return;
        setVerifying(true);
        setErrorMsg(null);
        try {
            const data = await verifyPublicTip(tipId, rawPaymentId);
            // Redirect to success page — it will re-verify and show correct status
            const qs = new URLSearchParams({ tip_id: tipId, payment_id: rawPaymentId }).toString();
            if (data.status === "approved" || data.status === "rejected" || data.status === "cancelled") {
                router.push(`/m/${slug}/tip/success?${qs}` as Route);
            } else {
                // Still pending — refresh query to re-check
                setVerifying(false);
                setErrorMsg("El pago sigue en proceso. Intenta en unos minutos.");
            }
        } catch {
            setVerifying(false);
            setErrorMsg("No se pudo verificar el estado. Intenta de nuevo.");
        }
    }

    return (
        <main className="flex min-h-screen flex-col items-center justify-center bg-neutral-950 text-white px-4">
            <div className="w-full max-w-sm rounded-2xl bg-neutral-900 p-8 text-center space-y-6 shadow-2xl">
                {/* Icon */}
                <div className="flex items-center justify-center">
                    <span className="flex h-16 w-16 items-center justify-center rounded-full bg-amber-500/20 text-4xl">
                        ⏳
                    </span>
                </div>

                {/* Heading */}
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">
                        Pago en proceso
                    </h1>
                    <p className="mt-2 text-neutral-400 text-sm">
                        Tu pago está siendo procesado por Mercado Pago.
                        Esto puede tardar unos minutos. ¡Gracias por tu propina!
                    </p>
                </div>

                {/* Reference */}
                {tipId && (
                    <p className="text-xs text-neutral-600 break-all">
                        Referencia: {tipId}
                    </p>
                )}

                {/* Error feedback */}
                {errorMsg && (
                    <p className="text-xs text-amber-400">{errorMsg}</p>
                )}

                {/* CTAs */}
                <div className="flex flex-col gap-3 pt-2">
                    {rawPaymentId ? (
                        <button
                            onClick={handleVerify}
                            disabled={verifying}
                            className="rounded-xl bg-violet-600 px-6 py-3 text-sm font-semibold text-white hover:bg-violet-500 disabled:opacity-60 transition-colors"
                        >
                            {verifying ? "Verificando…" : "Verificar estado"}
                        </button>
                    ) : (
                        <Link
                            href={`/m/${slug}/tip/success${tipId ? `?tip_id=${tipId}` : ""}` as Route}
                            className="rounded-xl bg-violet-600 px-6 py-3 text-sm font-semibold text-white hover:bg-violet-500 transition-colors"
                        >
                            Verificar estado
                        </Link>
                    )}
                    <Link
                        href={`/m/${slug}`}
                        className="rounded-xl bg-neutral-800 px-6 py-3 text-sm font-medium text-white hover:bg-neutral-700 transition-colors ring-1 ring-white/10"
                    >
                        Volver a la carta
                    </Link>
                </div>
            </div>

            {/* Powered by */}
            <p className="mt-8 text-xs text-neutral-600">
                Pagos procesados por Mercado Pago
            </p>
        </main>
    );
}
