import Link from 'next/link';
import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { getServiceEntryPath } from '@/lib/services';

export default async function ServiceHubPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const overview = session.services;

    if (!overview) {
        return (
            <section className="space-y-4">
                <header>
                    <p className="text-xs uppercase tracking-wide text-slate-400">Panel</p>
                    <h1 className="text-3xl font-semibold text-slate-900">Servicios</h1>
                    <p className="text-sm text-slate-500">No pudimos cargar la información. Reintentá en unos segundos.</p>
                </header>
            </section>
        );
    }

    const enabled = new Set(overview.enabled);
    const activeService = session.current.service;

    return (
        <section className="space-y-6">
            <header>
                <p className="text-xs uppercase tracking-wide text-slate-400">Panel</p>
                <h1 className="text-3xl font-semibold text-slate-900">Servicios habilitados</h1>
                <p className="text-sm text-slate-500">
                    Estado operativo para {session.current.business.name}. Entrá directo a cada servicio sin pasar por marketing.
                </p>
            </header>
            <div className="grid gap-4 md:grid-cols-2">
                {overview.available.map((service) => {
                    const isEnabled = enabled.has(service.slug);
                    const isActive = isEnabled && activeService === service.slug;
                    const entryPath = isEnabled ? getServiceEntryPath(service.slug) : undefined;
                    const statusLabel = isActive ? 'Operando' : isEnabled ? 'Listo' : 'No incluido';
                    const statusStyles = isActive
                        ? 'bg-brand-100 text-brand-700'
                        : isEnabled
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-slate-200 text-slate-600';

                    return (
                        <article key={service.slug} className="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                            <div className="space-y-3">
                                <div className="flex items-center gap-2">
                                    <h2 className="text-xl font-semibold text-slate-900">{service.name}</h2>
                                    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${statusStyles}`}>{statusLabel}</span>
                                </div>
                                <p className="text-sm text-slate-500">{service.description}</p>
                                <div className="flex flex-wrap gap-2">
                                    {service.features.map((feature) => (
                                        <span key={feature} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                                            {feature}
                                        </span>
                                    ))}
                                </div>
                            </div>
                            <div className="mt-6">
                                {entryPath ? (
                                    <Link
                                        href={entryPath}
                                        className="inline-flex w-full items-center justify-center rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
                                    >
                                        Ingresar
                                    </Link>
                                ) : (
                                    <p className="rounded-xl border border-dashed border-slate-200 px-4 py-2 text-center text-xs font-semibold text-slate-400">
                                        Coordiná con el equipo de Customer Success para habilitarlo.
                                    </p>
                                )}
                            </div>
                        </article>
                    );
                })}
            </div>
        </section>
    );
}
