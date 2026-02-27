import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { serverApiFetch } from '@/lib/api/server';
import type { MenuQrResponse } from '@/features/menu/types';
import Link from 'next/link';
import type { Route } from 'next';

export default async function MenuPreviewPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canView = session.permissions?.view_menu ?? false;
    if (!canView) {
        redirect('/app/servicios');
    }

    const businessId = session.current.business.id;
    let qrData: MenuQrResponse | null = null;

    try {
        qrData = await serverApiFetch<MenuQrResponse>(`/api/v1/menu-qr/${businessId}/`);
    } catch {
        // QR not generated yet — show empty state below
    }

    return (
        <section className="space-y-6">
            <header>
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-500">Menú Digital</p>
                <h1 className="text-3xl font-display font-bold text-slate-900">Vista previa del menú</h1>
            </header>

            {qrData?.public_url ? (
                <div className="space-y-4">
                    <div className="flex flex-wrap gap-3">
                        <a
                            href={qrData.public_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-2 rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 transition-colors"
                        >
                            Abrir menú público ↗
                        </a>
                        <Link
                            href={'/app/menu/qr' as Route}
                            className="rounded-full border border-slate-300 px-5 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
                        >
                            Ver código QR
                        </Link>
                    </div>

                    <div className="w-full overflow-hidden rounded-2xl border border-slate-200 shadow-sm">
                        <iframe
                            src={qrData.public_url}
                            title="Vista previa del menú"
                            className="h-[70vh] w-full"
                            style={{ border: 'none' }}
                        />
                    </div>
                </div>
            ) : (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-white/80 p-10 text-center">
                    <p className="text-slate-500">Tu menú todavía no está publicado.</p>
                    <p className="mt-1 text-sm text-slate-400">
                        Agregá productos desde la sección{' '}
                        <Link href="/app/menu" className="text-brand-600 hover:underline">
                            Menú
                        </Link>{' '}
                        y luego generá el QR.
                    </p>
                    <Link
                        href={'/app/menu/qr' as Route}
                        className="mt-6 inline-block rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white"
                    >
                        Generar QR
                    </Link>
                </div>
            )}
        </section>
    );
}
