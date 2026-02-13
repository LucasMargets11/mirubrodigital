import Link from 'next/link';

export default function SettingsPage() {
    return (
        <section className="space-y-6">
            <header>
                <h1 className="text-2xl font-semibold text-slate-900">Configuración</h1>
                <p className="text-sm text-slate-500">Administra tenants, usuarios y branding.</p>
            </header>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {/* Roles & Accesos */}
                <Link
                    href="/app/settings/access"
                    className="group rounded-xl border border-slate-200 bg-white p-6 hover:border-blue-300 hover:shadow-md transition-all"
                >
                    <div className="flex items-start gap-4">
                        <div className="rounded-lg bg-purple-100 p-3 text-purple-700 group-hover:bg-purple-200 transition-colors">
                            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"
                                />
                            </svg>
                        </div>
                        <div className="flex-1">
                            <h3 className="text-sm font-semibold text-slate-900 group-hover:text-blue-700 transition-colors">
                                Roles & Accesos
                            </h3>
                            <p className="mt-1 text-xs text-slate-500">
                                Administra roles, permisos y cuentas de usuarios
                            </p>
                        </div>
                    </div>
                </Link>

                {/* Sucursales */}
                <Link
                    href="/app/settings/branches"
                    className="group rounded-xl border border-slate-200 bg-white p-6 hover:border-blue-300 hover:shadow-md transition-all"
                >
                    <div className="flex items-start gap-4">
                        <div className="rounded-lg bg-blue-100 p-3 text-blue-700 group-hover:bg-blue-200 transition-colors">
                            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
                                />
                            </svg>
                        </div>
                        <div className="flex-1">
                            <h3 className="text-sm font-semibold text-slate-900 group-hover:text-blue-700 transition-colors">
                                Sucursales
                            </h3>
                            <p className="mt-1 text-xs text-slate-500">
                                Gestiona las sucursales de tu negocio
                            </p>
                        </div>
                    </div>
                </Link>

                {/* Menú Online */}
                <Link
                    href="/app/settings/online-menu"
                    className="group rounded-xl border border-slate-200 bg-white p-6 hover:border-blue-300 hover:shadow-md transition-all"
                >
                    <div className="flex items-start gap-4">
                        <div className="rounded-lg bg-green-100 p-3 text-green-700 group-hover:bg-green-200 transition-colors">
                            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
                                />
                            </svg>
                        </div>
                        <div className="flex-1">
                            <h3 className="text-sm font-semibold text-slate-900 group-hover:text-blue-700 transition-colors">
                                Menú Online
                            </h3>
                            <p className="mt-1 text-xs text-slate-500">
                                Configura tu menú QR y branding
                            </p>
                        </div>
                    </div>
                </Link>
            </div>

            <div className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">
                Más configuraciones próximamente.
            </div>
        </section>
    );
}
