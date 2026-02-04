'use client';

import { useMemo, useState, type ComponentType } from "react";
import { useQuery } from "@tanstack/react-query";
import { DollarSign, ShoppingCart, TrendingUp, FileText, AlertTriangle, Store } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DateRangePicker } from "@/components/ui/date-range-picker";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { apiGet } from "@/lib/api/client";
import { formatCurrency, formatNumber } from "@/lib/format";
import { branchService } from "@/services/branches";
import type { Branch } from "@/services/branches";

// We'll reuse existing reporting components or fetch data manually for the aggregated view
// Since this is a new feature, a simple dashboard is better than reusing complex components that rely on context hooks.

export default function OwnerOverviewPage() {
    const [dateRange, setDateRange] = useState<{ from: Date; to: Date }>(() => ({
        from: addDaysFromToday(-30),
        to: new Date(),
    }));

    // Scopes: 'children' (All) or 'selected' (Specific)
    const [selectedBranches, setSelectedBranches] = useState<string[]>([]);
    const [scopeMode, setScopeMode] = useState<'all' | 'specific'>('all');

    const { data: branches } = useQuery({
        queryKey: ['branches'],
        queryFn: branchService.list,
    });

    // Build query params
    const queryParams = useMemo(() => ({
        scope: scopeMode === 'all' ? 'children' : 'selected',
        business_ids: scopeMode === 'specific' ? selectedBranches.join(',') : undefined,
        from: formatForApi(dateRange.from),
        to: formatForApi(dateRange.to),
    }), [scopeMode, selectedBranches, dateRange]);

    const { data: summary, isLoading: isLoadingSummary } = useQuery({
        queryKey: ['owner-summary', queryParams],
        queryFn: async () => {
            const query = buildQueryString({ ...queryParams, group_by: 'day' });
            return apiGet<ReportSummaryResponse>(`/api/v1/reports/summary/${query}`);
        },
        enabled: !!branches,
    });

    const { data: stockAlerts, isLoading: isLoadingStockAlerts } = useQuery({
        queryKey: ['owner-stock-alerts', queryParams],
        queryFn: async () => {
            const query = buildQueryString({ ...queryParams, limit: 6 });
            return apiGet<StockAlertsResponse>(`/api/v1/reports/stock/alerts/${query}`);
        },
        enabled: !!branches,
    });
    const kpis = summary?.kpis ?? {};

    const toggleBranch = (id: string) => {
        setSelectedBranches(prev => {
            if (prev.includes(id)) {
                const next = prev.filter(x => x !== id);
                if (next.length === 0) {
                    setScopeMode('all');
                }
                return next;
            }
            setScopeMode('specific');
            return [...prev, id];
        });
    };

    const handleSelectAll = () => {
        setSelectedBranches([]);
        setScopeMode('all');
    }

    if (!branches) return <div>Cargando acceso a Matriz...</div>;

    const totalBranches = branches.length + 1; // HQ + sucursales

    return (
        <div className="space-y-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Sucursales</h1>
                    <p className="text-muted-foreground">Supervisa tus unidades, riesgos y ventas consolidadas.</p>
                </div>
                <div className="flex items-center gap-2">
                    <DateRangePicker
                        from={dateRange.from}
                        to={dateRange.to}
                        onSelect={(range) => {
                            if (range?.from && range?.to) setDateRange({ from: range.from, to: range.to });
                        }}
                    />
                </div>
            </div>

            {/* Filters */}
            <Card>
                <CardContent className="pt-6">
                    <div className="flex flex-wrap gap-2">
                        <Button
                            variant={scopeMode === 'all' ? 'default' : 'outline'}
                            size="sm"
                            onClick={handleSelectAll}
                        >
                            Todas ({totalBranches})
                        </Button>
                        {branches.map(b => (
                            <Button
                                key={b.id}
                                variant={selectedBranches.includes(String(b.id)) ? 'default' : 'outline'}
                                size="sm"
                                onClick={() => toggleBranch(String(b.id))}
                            >
                                {b.name}
                            </Button>
                        ))}
                    </div>
                </CardContent>
            </Card>

            {/* KPIS */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <KpiCard
                    title="Ventas Brutas"
                    value={kpis?.gross_sales_total}
                    icon={DollarSign}
                    loading={isLoadingSummary}
                    format="currency"
                />
                <KpiCard
                    title="Ventas Netas"
                    value={kpis?.net_sales_total}
                    icon={TrendingUp}
                    loading={isLoadingSummary}
                    format="currency"
                />
                <KpiCard
                    title="Tickets"
                    value={kpis?.sales_count}
                    icon={ShoppingCart}
                    loading={isLoadingSummary}
                    format="number"
                />
                <KpiCard
                    title="Ticket Promedio"
                    value={kpis?.avg_ticket}
                    icon={FileText}
                    loading={isLoadingSummary}
                    format="currency"
                />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
                <BranchesHealthCard branches={branches} totalBranches={totalBranches} scopeMode={scopeMode} selectedBranches={selectedBranches} />
                <CriticalAlertsCard data={stockAlerts} loading={isLoadingStockAlerts} />
            </div>

            {/* Tabs for details */}
            <Tabs defaultValue="sales" className="space-y-4">
                <TabsList>
                    <TabsTrigger value="sales">Ventas</TabsTrigger>
                    {/* Add Stock / Invoices later as separate components fetching with same queryParams */}
                </TabsList>
                <TabsContent value="sales">
                    <Card>
                        <CardHeader>
                            <CardTitle>Detalle Consolidados</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <p className="text-sm text-muted-foreground">
                                Los datos mostrados arriba corresponden a la suma de:
                                {scopeMode === 'all' ? ' Casa Matriz + Todas las sucursales' : ' Sucursales seleccionadas'}.
                            </p>
                            <SalesTrendList series={summary?.series} />
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
}

function KpiCard({ title, value, icon: Icon, loading, format = 'currency' }: KpiCardProps) {
    const formatted = formatValue(value, format);
    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{title}</CardTitle>
                <Icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
                <div className="text-2xl font-bold">{loading ? '...' : formatted}</div>
            </CardContent>
        </Card>
    )
}

function BranchesHealthCard({ branches, totalBranches, scopeMode, selectedBranches }: BranchesHealthCardProps) {
    const statusTotals = useMemo(() => {
        return branches.reduce<Record<string, number>>((acc, branch) => {
            const statusKey = (branch.status || 'desconocido').toLowerCase();
            acc[statusKey] = (acc[statusKey] ?? 0) + 1;
            return acc;
        }, {});
    }, [branches]);

    const orderedBranches = useMemo(() => {
        const selectedSet = new Set(selectedBranches);
        return [...branches].sort((a, b) => {
            const aSelected = selectedSet.has(String(a.id)) ? 0 : 1;
            const bSelected = selectedSet.has(String(b.id)) ? 0 : 1;
            if (aSelected !== bSelected) return aSelected - bSelected;
            return a.name.localeCompare(b.name);
        });
    }, [branches, selectedBranches]);

    const visibleBranches = orderedBranches.slice(0, 5);

    return (
        <Card>
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-semibold flex items-center gap-2">
                        <Store className="h-4 w-4 text-muted-foreground" />
                        Salud de Sucursales
                    </CardTitle>
                    <Badge variant="outline">{scopeMode === 'all' ? 'Todas' : `${selectedBranches.length} activas`}</Badge>
                </div>
                <p className="text-sm text-muted-foreground">{totalBranches} unidades habilitadas (incluye Casa Matriz).</p>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                    {Object.entries(statusTotals).map(([status, count]) => (
                        <div key={status} className="rounded-md border px-3 py-1">
                            <span className="font-semibold text-foreground mr-1">{count}</span>
                            {statusLabel(status)}
                        </div>
                    ))}
                    {Object.keys(statusTotals).length === 0 && (
                        <span>No hay sucursales auxiliares.</span>
                    )}
                </div>
                <div className="space-y-3">
                    {visibleBranches.map(branch => (
                        <div key={branch.id} className="flex items-center justify-between rounded-lg border px-3 py-2">
                            <div>
                                <p className="text-sm font-medium">{branch.name}</p>
                                <p className="text-xs text-muted-foreground">
                                    Alta {formatDateLabel(branch.created_at)}
                                </p>
                            </div>
                            <Badge variant={branch.status === 'active' ? 'secondary' : 'outline'}>
                                {statusLabel(branch.status)}
                            </Badge>
                        </div>
                    ))}
                    {visibleBranches.length === 0 && (
                        <p className="text-sm text-muted-foreground">Sin sucursales registradas aún.</p>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}

function CriticalAlertsCard({ data, loading }: CriticalAlertsCardProps) {
    const items = data?.items ?? [];
    return (
        <Card>
            <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base font-semibold">
                    <AlertTriangle className="h-4 w-4 text-destructive" />
                    Alertas críticas
                </CardTitle>
                <p className="text-sm text-muted-foreground">
                    Productos con riesgo en inventario dentro del alcance seleccionado.
                </p>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                    <AlertMetric label="Sin stock" value={data?.out_of_stock_count} loading={loading} variant="destructive" />
                    <AlertMetric label="Stock bajo" value={data?.low_stock_count} loading={loading} variant="secondary" />
                </div>
                <div className="space-y-3">
                    {loading && <p className="text-sm text-muted-foreground">Revisando inventario...</p>}
                    {!loading && items.length === 0 && (
                        <p className="text-sm text-muted-foreground">Sin alertas en el periodo analizado.</p>
                    )}
                    {items.map(item => (
                        <div key={`${item.product_id}-${item.name}`} className="flex items-center justify-between rounded-lg border px-3 py-2">
                            <div>
                                <p className="text-sm font-medium">{item.name}</p>
                                <p className="text-xs text-muted-foreground">Stock {item.stock} / Mín {item.threshold}</p>
                            </div>
                            <Badge variant={item.status === 'OUT' ? 'destructive' : 'secondary'}>
                                {item.status === 'OUT' ? 'Sin stock' : 'Stock bajo'}
                            </Badge>
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    );
}

function AlertMetric({ label, value, loading, variant }: AlertMetricProps) {
    return (
        <div className="rounded-lg border px-4 py-3">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="text-2xl font-semibold text-foreground">
                {loading ? '...' : formatNumber(value ?? 0)}
            </p>
            <Badge variant={variant} className="mt-2 w-fit">Prioridad</Badge>
        </div>
    );
}

function SalesTrendList({ series }: { series?: TrendPoint[] }) {
    if (!series || series.length === 0) {
        return <p className="text-sm text-muted-foreground">Aún no hay datos suficientes para graficar.</p>;
    }

    const recent = series.slice(-4);

    return (
        <div className="mt-4 space-y-3">
            {recent.map(point => (
                <div key={point.period} className="flex items-center justify-between rounded-lg border px-3 py-2">
                    <div>
                        <p className="text-sm font-medium">{formatPeriod(point.period)}</p>
                        <p className="text-xs text-muted-foreground">Tickets {formatNumber(point.sales_count)}</p>
                    </div>
                    <span className="text-sm font-semibold">{formatCurrency(point.gross_sales)}</span>
                </div>
            ))}
        </div>
    );
}

const MS_PER_DAY = 24 * 60 * 60 * 1000;

function addDaysFromToday(deltaDays: number) {
    const now = new Date();
    return new Date(now.getTime() + deltaDays * MS_PER_DAY);
}

function formatForApi(date?: Date) {
    if (!date) return undefined;
    return date.toISOString().split('T')[0];
}

function buildQueryString(params: Record<string, string | number | undefined>) {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
            search.append(key, String(value));
        }
    });
    const serialized = search.toString();
    return serialized ? `?${serialized}` : '';
}

function formatValue(value: string | number | undefined, format: 'currency' | 'number') {
    if (value === undefined || value === null) {
        return format === 'currency' ? formatCurrency(0) : formatNumber(0);
    }
    return format === 'currency' ? formatCurrency(value) : formatNumber(value);
}

function statusLabel(status?: string) {
    const normalized = (status || '').toLowerCase();
    const labels: Record<string, string> = {
        active: 'Operativa',
        inactive: 'Inactiva',
        pending: 'Pendiente',
        suspended: 'Suspendida',
        desconocido: 'Sin estado',
    };
    return labels[normalized] ?? status?.toUpperCase() ?? 'Sin estado';
}

function formatDateLabel(value?: string) {
    if (!value) return 'Fecha desconocida';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'Fecha desconocida';
    return date.toLocaleDateString('es-AR', { day: 'numeric', month: 'short', year: 'numeric' });
}

function formatPeriod(value: string) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }
    return date.toLocaleDateString('es-AR', { weekday: 'short', day: 'numeric', month: 'short' });
}

type TrendPoint = {
    period: string;
    gross_sales: string;
    sales_count: number;
    avg_ticket: string;
};

type ReportSummaryResponse = {
    kpis: Record<string, string | number>;
    series: TrendPoint[];
};

type StockAlertsResponse = {
    low_stock_threshold_default: string;
    out_of_stock_count: number;
    low_stock_count: number;
    items: StockAlertItem[];
};

type StockAlertItem = {
    product_id: string;
    name: string;
    stock: string;
    threshold: string;
    status: 'OUT' | 'LOW';
};

type BranchesHealthCardProps = {
    branches: Branch[];
    totalBranches: number;
    scopeMode: 'all' | 'specific';
    selectedBranches: string[];
};

type CriticalAlertsCardProps = {
    data?: StockAlertsResponse;
    loading: boolean;
};

type AlertMetricProps = {
    label: string;
    value?: number;
    loading: boolean;
    variant: 'destructive' | 'secondary';
};

type KpiCardProps = {
    title: string;
    value?: string | number;
    icon: ComponentType<{ className?: string }>;
    loading: boolean;
    format: 'currency' | 'number';
};
