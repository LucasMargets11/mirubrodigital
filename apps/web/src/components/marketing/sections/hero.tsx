import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { HERO_PROOF_POINTS } from './data';

const DASHBOARD_STATS = [
    { label: 'Ventas hoy', value: '$ 542k', trend: '+18% vs ayer' },
    { label: 'Pedidos activos', value: '126', trend: '9 pendientes' },
];

const CASH_SESSIONS = [
    { name: 'Caja Palermo', amount: '$ 89k', status: 'Abierta' },
    { name: 'Caja Centro', amount: '$ 74k', status: 'Cierre programado' },
    { name: 'Caja Take Away', amount: '$ 51k', status: 'Conciliando' },
];

export function HeroSection() {
    return (
        <section className="relative overflow-hidden py-16 lg:py-20">
            <div className="absolute inset-0 -z-10 bg-gradient-to-br from-slate-50 via-white to-slate-50" />
            <div className="mx-auto max-w-7xl px-6 lg:px-10">
                <div className="grid gap-12 lg:grid-cols-2 lg:gap-16">
                    <div className="max-w-xl space-y-6">
                        <Badge variant="secondary" className="bg-primary/10 text-primary">
                            SaaS multi-tenant
                        </Badge>
                        <div className="space-y-4">
                            <h1 className="text-4xl font-display font-bold text-zinc-900 sm:text-5xl">
                                Centraliza tus operaciones en minutos
                            </h1>
                            <p className="text-lg text-zinc-600">
                                Lanza áreas de marketing y operación con una base lista para equipos modernos: cajas, stock, menús y reportes conectados.
                            </p>
                        </div>
                        <div className="flex flex-wrap gap-4">
                            <Button asChild size="lg">
                                <Link href="/app">Ir al panel</Link>
                            </Button>
                            <Button asChild variant="outline" size="lg">
                                <Link href="/pricing">Ver precios</Link>
                            </Button>
                        </div>
                        <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-zinc-500">
                            {HERO_PROOF_POINTS.map((point) => (
                                <span key={point} className="flex items-center gap-2">
                                    <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
                                    {point}
                                </span>
                            ))}
                        </div>
                    </div>

                    <div className="w-full max-w-[640px] justify-self-end">
                        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/60">
                            <div className="space-y-5">
                                <div>
                                    <p className="text-xs uppercase tracking-[0.2em] text-primary">Mirubro insights</p>
                                    <h3 className="mt-2 text-xl font-semibold text-zinc-900">Panel operativo</h3>
                                    <p className="text-sm text-zinc-500">Vista consolidada de todas las unidades de negocio.</p>
                                </div>
                                <div className="grid gap-4 sm:grid-cols-2">
                                    {DASHBOARD_STATS.map((stat) => (
                                        <Card key={stat.label} className="border-slate-200 bg-white/90 p-4">
                                            <p className="text-xs uppercase tracking-wide text-zinc-500">{stat.label}</p>
                                            <p className="mt-2 text-2xl font-semibold text-zinc-900">{stat.value}</p>
                                            <p className="text-sm text-emerald-600">{stat.trend}</p>
                                        </Card>
                                    ))}
                                </div>
                                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                                    <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-zinc-500">
                                        <span>Sesiones de caja</span>
                                        <span>Estado</span>
                                    </div>
                                    <div className="mt-4 space-y-3">
                                        {CASH_SESSIONS.map((session) => (
                                            <div key={session.name} className="flex items-center justify-between rounded-xl bg-white p-3 text-sm shadow-sm">
                                                <div>
                                                    <p className="font-medium text-zinc-900">{session.name}</p>
                                                    <p className="text-xs text-zinc-500">{session.amount}</p>
                                                </div>
                                                <span className="text-xs font-semibold text-primary">{session.status}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                                <div className="rounded-2xl border border-slate-200 bg-white/90 p-4">
                                    <p className="text-sm font-semibold text-zinc-900">Pronóstico semanal</p>
                                    <div className="mt-3 grid grid-cols-3 gap-3 text-center text-xs text-zinc-500">
                                        <div>
                                            <p className="text-lg font-semibold text-zinc-900">+12%</p>
                                            <p>Crecimiento</p>
                                        </div>
                                        <div>
                                            <p className="text-lg font-semibold text-zinc-900">8</p>
                                            <p>Sucursales</p>
                                        </div>
                                        <div>
                                            <p className="text-lg font-semibold text-zinc-900">4.7</p>
                                            <p>NPS</p>
                                        </div>
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
