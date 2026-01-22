import { serverApiFetch } from '@/lib/api/server';

type InventorySummary = {
    total_products: number;
    low_stock: number;
    out_of_stock: number;
};

export default async function GestionDashboardPage() {
    let summary: InventorySummary | null = null;
    try {
        summary = await serverApiFetch<InventorySummary>('/api/v1/inventory/summary/');
    } catch (error) {
        summary = null;
    }

    return (
        <div className="space-y-6">
            <section>
                <h2 className="text-lg font-semibold text-slate-900">Salud del catálogo</h2>
                <div className="mt-4 grid gap-4 md:grid-cols-3">
                    {[
                        { label: 'Productos publicados', value: summary?.total_products ?? 0 },
                        { label: 'Stock crítico', value: summary?.low_stock ?? 0 },
                        { label: 'Sin stock', value: summary?.out_of_stock ?? 0 },
                    ].map((item) => (
                        <article key={item.label} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                            <p className="text-xs uppercase tracking-wide text-slate-400">{item.label}</p>
                            <p className="mt-2 text-3xl font-semibold text-slate-900">{item.value}</p>
                        </article>
                    ))}
                </div>
            </section>
            <section className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-6">
                    <h3 className="text-base font-semibold text-slate-900">Siguientes pasos sugeridos</h3>
                    <ol className="mt-4 space-y-3 text-sm text-slate-600">
                        <li>1. Cargar productos con costos y precios actualizados.</li>
                        <li>2. Registrar un movimiento inicial de inventario.</li>
                        <li>3. Configurar alertas de stock mínimo para tu equipo.</li>
                    </ol>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-gradient-to-br from-amber-50 to-amber-100 p-6">
                    <h3 className="text-base font-semibold text-amber-900">Checklist de lanzamiento</h3>
                    <ul className="mt-4 space-y-2 text-sm text-amber-900">
                        <li>☑️ Roles y permisos asignados.</li>
                        <li>☑️ Plan activo y servicios habilitados.</li>
                        <li>⬜ Integrar ventas/caja (próximamente).</li>
                    </ul>
                </div>
            </section>
        </div>
    );
}
