import { Branch } from "@/services/branches";
import { useQuery } from "@tanstack/react-query";
import { branchService } from "@/services/branches";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DateRangePicker } from "@/components/ui/date-range-picker";
import { useState } from "react";
import { addDays, format } from "date-fns";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api"; 
import { toast } from "sonner";
import { DollarSign, ShoppingCart, TrendingUp, Package, FileText } from "lucide-react";
import { getCookie } from "cookies-next";

// We'll reuse existing reporting components or fetch data manually for the aggregated view
// Since this is a new feature, a simple dashboard is better than reusing complex components that rely on context hooks.

export default function OwnerOverviewPage() {
    const [dateRange, setDateRange] = useState<{ from: Date; to: Date }>({
        from: addDays(new Date(), -30),
        to: new Date(),
    });
    
    // Scopes: 'children' (All) or 'selected' (Specific)
    const [selectedBranches, setSelectedBranches] = useState<string[]>([]); // Empty means all? Or logic below.
    const [scopeMode, setScopeMode] = useState<'all' | 'specific'>('all');

    const { data: branches } = useQuery({
        queryKey: ['branches'],
        queryFn: branchService.list,
    });

    // Build query params
    const queryParams = {
        scope: scopeMode === 'all' ? 'children' : 'selected',
        business_ids: scopeMode === 'specific' ? selectedBranches.join(',') : undefined,
        from: dateRange.from ? format(dateRange.from, 'yyyy-MM-dd') : undefined,
        to: dateRange.to ? format(dateRange.to, 'yyyy-MM-dd') : undefined,
    };

    // Fetch Aggregated Reports
    const { data: kpis, isLoading: isLoadingKpis } = useQuery({
        queryKey: ['owner-kpis', queryParams],
        queryFn: async () => {
             const res = await api.get('/api/v1/reports/sales', { params: queryParams });
             return res.data.kpis;
        },
        enabled: !!branches, // Only fetch if we can confirm we are HQ (branches list success)
    });

    const toggleBranch = (id: string) => {
        setSelectedBranches(prev => 
            prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
        );
        setScopeMode('specific');
    };

    const handleSelectAll = () => {
        setSelectedBranches([]);
        setScopeMode('all');
    }

    if (!branches) return <div>Cargando acceso a Matriz...</div>;

    return (
        <div className="space-y-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Panel General (HQ)</h1>
                    <p className="text-muted-foreground">Visión consolidada de todas las sucursales.</p>
                </div>
                <div className="flex items-center gap-2">
                    <DateRangePicker 
                         from={dateRange.from}
                         to={dateRange.to}
                         onSelect={(range) => {
                             if(range?.from && range?.to) setDateRange({ from: range.from, to: range.to });
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
                            Todas ({branches.length + 1})
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
                    loading={isLoadingKpis} 
                />
                 <KpiCard 
                    title="Ventas Netas" 
                    value={kpis?.net_sales_total} 
                    icon={TrendingUp} 
                    loading={isLoadingKpis} 
                />
                 <KpiCard 
                    title="Tickets" 
                    value={kpis?.sales_count} 
                    icon={ShoppingCart} 
                    loading={isLoadingKpis} 
                />
                <KpiCard 
                    title="Ticket Promedio" 
                    value={kpis?.avg_ticket} 
                    icon={FileText} 
                    loading={isLoadingKpis} 
                />
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
                            {/* Here we could render the chart or list */}
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
}

function KpiCard({ title, value, icon: Icon, loading }: any) {
    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{title}</CardTitle>
                <Icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
                <div className="text-2xl font-bold">{loading ? '...' : value || '$0.00'}</div>
            </CardContent>
        </Card>
    )
}
