"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { getPublicTipStatus, verifyPublicTip } from "@/features/menu/api";
import type { TipVerifyResponse } from "@/features/menu/types";

// ─── Poll config (fallback when no payment_id in query) ──────────────────────
const POLL_INTERVAL_MS = 3000;
const MAX_POLL_ATTEMPTS = 10;

// ─── Helpers ─────────────────────────────────────────────────────────────────
function formatAmount(amount: string, currency: string) {
    const num = parseFloat(amount);
    const formatted = new Intl.NumberFormat("es-AR", {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
    }).format(num);
    return `${currency === "ARS" ? "$" : currency} ${formatted}`;
}

type VerifyStatus = "idle" | "loading" | "success" | "mismatch" | "error";

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function TipSuccessPage() {
    const params = useParams<{ slug: string }>();
    const searchParams = useSearchParams();
    const slug = params.slug;
    const tipId = searchParams.get("tip_id");
    // MP returns payment_id (preferred) or collection_id (alias) in back_urls
    const rawPaymentId =
        searchParams.get("payment_id") ?? searchParams.get("collection_id") ?? null;

    const [tip, setTip] = useState<TipVerifyResponse | null>(null);
    const [verifyStatus, setVerifyStatus] = useState<VerifyStatus>("idle");
    const [errorMsg, setErrorMsg] = useState<string | null>(null);

    // ─── Verify via payment_id (fast path — no webhook needed) ────────────
    const runVerify = useCallback(async (payId: string) => {
        if (!tipId) return;
        setVerifyStatus("loading");
        setErrorMsg(null);
        try {
            const data = await verifyPublicTip(tipId, payId);
            setTip(data);
            setVerifyStatus("success");
        } catch (err: unknown) {
            const status = (err as { status?: number })?.status;
            if (status === 400) {
                setVerifyStatus("mismatch");
                setErrorMsg("El pago no corresponde a esta propina.");
            } else {
                setVerifyStatus("error");
                setErrorMsg("No se pudo verificar el pago con Mercado Pago.");
            }
        }
    }, [tipId]);

    // ─── Fallback: poll /status (when no payment_id in query) ─────────────
    useEffect(() => {
        if (!tipId) {
            setVerifyStatus("error");
            setErrorMsg("No se encontró el ID de la propina.");
            return;
        }

        // Fast path: use payment_id from query string to call verify
        if (rawPaymentId) {
            runVerify(rawPaymentId);
            return;
        }

        // Slow path: poll /status (webhook-less fallback, ~30 s max)
        let attempts = 0;
        let timeoutId: ReturnType<typeof setTimeout>;
        setVerifyStatus("loading");

        async function poll() {
            try {
                const data = await getPublicTipStatus(tipId!);
                // Adapt TipTransaction shape to TipVerifyResponse shape
                setTip({
                    tip_id: data.id,
                    status: data.status,
                    mp_payment_id: null,
                    amount: data.amount,
                    currency: data.currency,
                    mp_status: data.status,
                    mp_status_detail: "",
                    verified_at: data.created_at,
                });
                if (
                    (data.status === "created" || data.status === "pending") &&
                    attempts < MAX_POLL_ATTEMPTS
                ) {
                    attempts++;
                    timeoutId = setTimeout(poll, POLL_INTERVAL_MS);
                } else {
                    setVerifyStatus("success");
                }
            } catch {
                setVerifyStatus("error");
                setErrorMsg("No se pudo verificar el estado del pago.");
            }
        }

        poll();
        return () => clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [tipId]);

    // ─── Loading state ──────────────────────────────────────────────────────
    if (verifyStatus === "idle" || verifyStatus === "loading") {
        return (
            <main className="flex min-h-screen flex-col items-center justify-center bg-neutral-950 text-white px-4">
                <div className="flex flex-col items-center gap-4">
                    <span className="inline-block h-10 w-10 animate-spin rounded-full border-4 border-violet-500 border-t-transparent" />
                    <p className="text-neutral-400 text-sm">Verificando tu pago…</p>
                </div>
            </main>
        );
    }

    // ─── Mismatch / error state ─────────────────────────────────────────────
    if (verifyStatus === "mismatch" || (verifyStatus === "error" && !tip)) {
        return (
            <main className="flex min-h-screen flex-col items-center justify-center bg-neutral-950 text-white px-4 text-center">
                <div className="w-full max-w-sm rounded-2xl bg-neutral-900 p-8 space-y-6 shadow-2xl">
                    <span className="flex mx-auto h-16 w-16 items-center justify-center rounded-full bg-red-500/20 text-4xl">
                        ⚠️
                    </span>
                    <p className="text-neutral-300 text-sm">{errorMsg ?? "No pudimos verificar el pago."}</p>
                    <div className="flex flex-col gap-3">
                        {rawPaymentId && (
                            <button
                                onClick={() => runVerify(rawPaymentId)}
                                className="rounded-xl bg-violet-600 px-6 py-3 text-sm font-semibold text-white hover:bg-violet-500 transition-colors"
                            >
                                Reintentar verificación
                            </button>
                        )}
                        <Link
                            href={`/m/${slug}`}
                            className="rounded-xl bg-neutral-800 px-6 py-3 text-sm font-medium text-white hover:bg-neutral-700 transition-colors ring-1 ring-white/10"
                        >
                            Volver a la carta
                        </Link>
                    </div>
                </div>
            </main>
        );
    }

    // ─── Result state ────────────────────────────────────────────────────────
    const tipStatus = tip?.status ?? "pending";
    const isApproved = tipStatus === "approved";
    const isRejected = tipStatus === "rejected" || tipStatus === "cancelled";
    const isPending = !isApproved && !isRejected;

    return (
        <main className="flex min-h-screen flex-col items-center justify-center bg-neutral-950 text-white px-4">
            <div className="w-full max-w-sm rounded-2xl bg-neutral-900 p-8 text-center space-y-6 shadow-2xl">
                {/* Icon */}
                <div className="flex items-center justify-center">
                    {isApproved ? (
                        <span className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/20 text-4xl">✅</span>
                    ) : isRejected ? (
                        <span className="flex h-16 w-16 items-center justify-center rounded-full bg-red-500/20 text-4xl">❌</span>
                    ) : (
                        <span className="flex h-16 w-16 items-center justify-center rounded-full bg-amber-500/20 text-4xl">⏳</span>
                    )}
                </div>

                {/* Heading */}
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">
                        {isApproved
                            ? "¡Gracias por tu propina!"
                            : isRejected
                            ? "Pago no completado"
                            : "Pago en proceso"}
                    </h1>
                    <p className="mt-2 text-neutral-400 text-sm">
                        {isApproved && tip
                            ? `Recibimos ${formatAmount(tip.amount, tip.currency)} 🙌`
                            : isRejected
                            ? "El pago fue rechazado o cancelado por Mercado Pago."
                            : "Tu pago está siendo procesado. Puede tardar unos minutos."}
                    </p>
                </div>

                {/* Amount chip — only on approved */}
                {isApproved && tip && (
                    <div className="inline-block rounded-full bg-violet-600/20 px-5 py-2 text-lg font-semibold text-violet-300 ring-1 ring-violet-500/40">
                        {formatAmount(tip.amount, tip.currency)}
                    </div>
                )}

                {/* CTAs */}
                <div className="flex flex-col gap-3 pt-2">
                    {isPending && rawPaymentId && (
                        <button
                            onClick={() => runVerify(rawPaymentId)}
                            className="rounded-xl bg-violet-600 px-6 py-3 text-sm font-semibold text-white hover:bg-violet-500 transition-colors"
                        >
                            Verificar estado
                        </button>
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
