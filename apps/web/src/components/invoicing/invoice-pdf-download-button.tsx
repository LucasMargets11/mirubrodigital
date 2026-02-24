"use client";

/**
 * Botón para descargar el PDF de una factura.
 *
 * Maneja el flujo de descarga e interpreta los errores del backend:
 * - 422 issuer_profile_incomplete → muestra aviso con link a Configuración
 * - Otros errores → mensaje genérico
 */
import Link from 'next/link';

import { useDownloadInvoicePdf } from '@/features/invoices/hooks';

type Props = {
    invoiceId: string;
    /** Estilo del botón. 'default' = enlace sutil, 'btn' = botón con borde. */
    variant?: 'default' | 'btn';
    children?: React.ReactNode;
};

const MISSING_FIELD_LABELS: Record<string, string> = {
    legal_name: 'Razón social',
    fiscal_address: 'Domicilio fiscal',
    commercial_address: 'Domicilio comercial',
    tax_id: 'CUIT / Identificación fiscal',
    vat_condition: 'Condición ante IVA',
};

export function InvoicePdfDownloadButton({ invoiceId, variant = 'default', children }: Props) {
    const { download, isLoading, error, clearError } = useDownloadInvoicePdf();

    const handleClick = () => {
        void download(invoiceId);
    };

    const buttonClass =
        variant === 'btn'
            ? 'rounded-full border border-slate-200 px-4 py-2 text-center text-sm font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900 disabled:cursor-not-allowed disabled:text-slate-300'
            : 'text-slate-600 hover:text-slate-900 text-sm font-semibold';

    return (
        <span className="inline-flex flex-col gap-2">
            <button
                type="button"
                onClick={handleClick}
                disabled={isLoading}
                className={buttonClass}
            >
                {isLoading ? 'Descargando...' : (children ?? 'Descargar PDF')}
            </button>

            {error ? (
                <span className="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                    {error.type === 'issuer_profile_incomplete' ? (
                        <>
                            <strong className="block font-semibold">
                                Completá el Perfil Fiscal para descargar la factura.
                            </strong>
                            {error.missing_fields.length > 0 ? (
                                <span className="block mt-0.5">
                                    Faltan: {error.missing_fields
                                        .map((f) => MISSING_FIELD_LABELS[f] ?? f)
                                        .join(', ')}.
                                </span>
                            ) : null}
                            <Link
                                href="/app/gestion/configuracion/negocio"
                                className="mt-1 block font-semibold underline hover:text-rose-800"
                                onClick={clearError}
                            >
                                Completar datos del negocio →
                            </Link>
                        </>
                    ) : (
                        <>
                            <span>{error.message}</span>
                            <button
                                type="button"
                                onClick={clearError}
                                className="ml-2 underline hover:text-rose-800"
                            >
                                Cerrar
                            </button>
                        </>
                    )}
                </span>
            ) : null}
        </span>
    );
}
